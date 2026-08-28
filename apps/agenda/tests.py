"""Tests du domaine « Agenda » : inscriptions du public (VIT-2).

Le point dur n'est pas la règle — « on ne dépasse pas la jauge » se lit d'un
trait — mais sa tenue quand deux personnes visent la dernière place au même
instant. Ce cas ne s'observe que sur PostgreSQL : sous SQLite,
`select_for_update` ne fait rien.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from django.utils.timezone import make_aware

from apps.agenda.models import Evenement, Inscription
from apps.agenda.services import (
    InscriptionFermee,
    PlusAssezDePlaces,
    annuler_inscription,
    inscrire,
    places_prises,
    places_restantes,
)


def _evenement(places_max=None, titre="Représentation"):
    return Evenement.objects.create(
        titre=titre,
        date_debut=make_aware(datetime(2026, 11, 1, 20, 0)),
        places_max=places_max,
        statut_moderation=Evenement.StatutModeration.PUBLIE,
    )


def test_sans_jauge_l_evenement_n_accueille_pas_d_inscription(db):
    evenement = _evenement(places_max=None)
    with pytest.raises(InscriptionFermee):
        inscrire(evenement, nom="Camille", email="c@example.org")
    assert places_restantes(evenement) is None


def test_inscription_decompte_les_places(db):
    evenement = _evenement(places_max=10)
    inscrire(evenement, nom="Camille", email="c@example.org", places=3)
    assert places_prises(evenement) == 3
    assert places_restantes(evenement) == 7


def test_on_ne_depasse_pas_la_jauge(db):
    evenement = _evenement(places_max=5)
    inscrire(evenement, nom="Camille", email="c@example.org", places=4)
    with pytest.raises(PlusAssezDePlaces):
        inscrire(evenement, nom="Dominique", email="d@example.org", places=2)
    assert places_prises(evenement) == 4


def test_un_evenement_complet_refuse_toute_place(db):
    evenement = _evenement(places_max=2)
    inscrire(evenement, nom="Camille", email="c@example.org", places=2)
    with pytest.raises(PlusAssezDePlaces) as erreur:
        inscrire(evenement, nom="Dominique", email="d@example.org")
    assert "complet" in str(erreur.value)


def test_une_annulation_rend_ses_places(db):
    evenement = _evenement(places_max=4)
    inscription = inscrire(evenement, nom="Camille", email="c@example.org", places=4)
    assert places_restantes(evenement) == 0

    annuler_inscription(inscription)

    assert places_restantes(evenement) == 4
    # Marquée, pas supprimée : le bureau garde l'historique de la soirée.
    assert Inscription.objects.filter(pk=inscription.pk).exists()


def test_annuler_deux_fois_ne_rend_pas_les_places_en_double(db):
    evenement = _evenement(places_max=4)
    inscription = inscrire(evenement, nom="Camille", email="c@example.org", places=2)

    annuler_inscription(inscription)
    annuler_inscription(inscription)

    assert places_restantes(evenement) == 4


def test_chaque_inscription_porte_un_jeton_unique(db):
    evenement = _evenement(places_max=10)
    a = inscrire(evenement, nom="Camille", email="c@example.org")
    b = inscrire(evenement, nom="Dominique", email="d@example.org")
    assert a.jeton != b.jeton


# --- Concurrence réelle (PostgreSQL uniquement) ------------------------------

NB_CANDIDATS = 8


@pytest.mark.django_db(transaction=True)
def test_une_seule_reservation_passe_sur_la_derniere_place():
    """Huit personnes visent la même dernière place : une seule l'obtient.

    C'est la vérification que la fiche VIT-2 réclamait « sous concurrence
    réelle, pas en séquentiel » — et elle est impossible à faire tenir sans
    verrou : sans lui, les huit lisent « il reste une place » avant qu'aucune
    n'ait écrit."""
    import threading

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip(
            "select_for_update est un no-op sur SQLite : le test passerait "
            "sans rien prouver. Relancer avec TEST_POSTGRES=1."
        )

    evenement = _evenement(places_max=1)
    barriere = threading.Barrier(NB_CANDIDATS)
    obtenues, refusees = [], []

    def tenter(indice):
        try:
            barriere.wait(timeout=10)
            obtenues.append(
                inscrire(evenement, nom=f"Spectateur {indice}", email=f"s{indice}@example.org")
            )
        except PlusAssezDePlaces:
            refusees.append(indice)
        finally:
            connections.close_all()

    fils = [threading.Thread(target=tenter, args=(i,)) for i in range(NB_CANDIDATS)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)

    assert len(obtenues) == 1, f"{len(obtenues)} réservations acceptées pour 1 place"
    assert len(refusees) == NB_CANDIDATS - 1
    assert places_prises(evenement) == 1


# --- Purge RGPD --------------------------------------------------------------


def _passe(jours):
    from django.utils import timezone

    return timezone.now() - timezone.timedelta(days=jours)


def test_la_purge_ne_supprime_rien_sans_le_drapeau(db):
    from django.core.management import call_command

    evenement = Evenement.objects.create(titre="Vieille", date_debut=_passe(200), places_max=10)
    inscrire(evenement, nom="Camille", email="c@example.org")

    call_command("purger_inscriptions", "--jours", "90")

    assert Inscription.objects.count() == 1


def test_la_purge_efface_les_inscriptions_des_evenements_passes(db):
    from django.core.management import call_command

    vieux = Evenement.objects.create(titre="Vieille", date_debut=_passe(200), places_max=10)
    recent = Evenement.objects.create(titre="Récente", date_debut=_passe(10), places_max=10)
    inscrire(vieux, nom="Camille", email="c@example.org")
    gardee = inscrire(recent, nom="Dominique", email="d@example.org")

    call_command("purger_inscriptions", "--jours", "90", "--pour-de-vrai")

    # La date de l'ÉVÉNEMENT fait foi : la soirée récente garde ses inscrits.
    assert list(Inscription.objects.all()) == [gardee]


def test_une_jauge_reduite_sous_les_places_prises_ne_casse_rien(db):
    """Cas réel : le bureau réduit la jauge après des réservations. On ne
    réécrit pas l'histoire — les places déjà prises le restent — mais plus
    aucune nouvelle ne passe."""
    evenement = _evenement(places_max=60)
    inscrire(evenement, nom="Camille", email="c@example.org", places=20)

    evenement.places_max = 10
    evenement.save(update_fields=["places_max"])

    assert places_prises(evenement) == 20
    assert places_restantes(evenement) == 0  # jamais négatif
    with pytest.raises(PlusAssezDePlaces):
        inscrire(evenement, nom="Dominique", email="d@example.org")


def test_une_meme_adresse_peut_reserver_plusieurs_fois(db):
    """Comportement assumé : la borne de dix places vaut PAR RÉSERVATION, pas
    par personne — un même foyer peut revenir en prendre d'autres. Bloquer par
    e-mail donnerait une fausse sécurité (on en change en une seconde) tout en
    gênant un cas légitime. Seule la jauge fait autorité."""
    evenement = _evenement(places_max=50)

    for _ in range(3):
        inscrire(evenement, nom="Camille", email="camille@example.org", places=10)

    assert places_prises(evenement) == 30
    assert Inscription.objects.count() == 3
