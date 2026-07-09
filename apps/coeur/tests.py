"""Tests du module de rôles (`apps.coeur.roles`) et des signataires."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.coeur.models import Membre, Signataire, Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU, est_bureau
from apps.coeur.services import (
    OuvertureCompteImpossible,
    creer_membre,
    membres_en_vedette,
    ouvrir_compte,
    synchroniser_compte,
)


def test_utilisateur_lambda_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(username="lambda", password="x")
    assert est_bureau(user) is False


def test_membre_du_groupe_bureau_est_bureau(db):
    user = Utilisateur.objects.create_user(username="secretaire", password="x")
    groupe, _ = Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)
    user.groups.add(groupe)
    assert est_bureau(user) is True


def test_staff_est_bureau(db):
    user = Utilisateur.objects.create_user(username="admin", password="x", is_staff=True)
    assert est_bureau(user) is True


def test_compte_inactif_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(
        username="ancien", password="x", is_staff=True, is_active=False
    )
    assert est_bureau(user) is False


def test_signataire_image_base64_renvoie_un_data_uri(db):
    sig = Signataire.objects.create(
        nom="Alice",
        qualite="Présidente",
        signature_image=SimpleUploadedFile("sig.png", b"\x89PNG-faux", content_type="image/png"),
    )
    uri = sig.image_base64()
    assert uri.startswith("data:image/png;base64,")


def test_signataire_sans_image_renvoie_chaine_vide(db):
    sig = Signataire.objects.create(nom="Bob", qualite="Trésorier")
    assert sig.image_base64() == ""


# --- Sélection des membres en vedette (page association) -------------------


def _membre_vedette(nom, *, visible=True, une=False):
    user = Utilisateur.objects.create(username=nom, last_name=nom)
    return Membre.objects.create(user=user, nom=nom, visible_sur_site=visible, mis_en_avant=une)


def test_vedette_inclut_les_a_la_une_et_complete_au_hasard(db):
    une1 = _membre_vedette("une1", une=True)
    une2 = _membre_vedette("une2", une=True)
    for i in range(5):
        _membre_vedette(f"autre{i}")

    vedette = membres_en_vedette(nombre=4)
    assert len(vedette) == 4
    assert une1 in vedette and une2 in vedette  # les « à la une » d'abord
    assert all(m.visible_sur_site for m in vedette)  # complété par des visibles


def test_vedette_exclut_les_membres_masques(db):
    cache_une = _membre_vedette("cacheune", visible=False, une=True)
    visible = _membre_vedette("visible")
    vedette = membres_en_vedette(nombre=6)
    assert cache_une not in vedette  # masqué, même « à la une »
    assert visible in vedette


def test_vedette_bornee_au_nombre(db):
    for i in range(10):
        _membre_vedette(f"m{i}", une=True)
    assert len(membres_en_vedette(nombre=6)) == 6


# --- Membre = personne : identité sur la fiche, compte optionnel -----------


def test_creer_membre_sans_compte(db):
    """Une fiche adhérent existe sans compte de connexion."""
    membre = creer_membre(prenom="Zoé", nom="Nadal", email="zoe@example.org")
    assert membre.user_id is None
    assert membre.a_un_compte is False
    assert membre.nom_complet == "Zoé Nadal"
    assert str(membre) == "Zoé Nadal"
    assert Utilisateur.objects.count() == 0  # aucun compte créé


def test_str_membre_robuste_sans_identite(db):
    """`__str__` ne casse jamais : identité vide et sans compte → libellé de repli."""
    membre = creer_membre(prenom="", nom="", email="")
    assert str(membre) == "Nouveau membre"


def test_nom_liste_met_le_nom_de_famille_en_premier(db):
    """Pour les listes triées par nom : « Nom Prénom » (nom de famille d'abord)."""
    membre = creer_membre(prenom="Zoé", nom="Nadal")
    assert membre.nom_liste == "Nadal Zoé"
    assert creer_membre(prenom="", nom="").nom_liste == "Nouveau membre"  # repli


def test_ouvrir_compte_cree_le_compte_et_recopie_l_identite(db):
    membre = creer_membre(prenom="Zoé", nom="Nadal", email="zoe@example.org")
    uidb64, token = ouvrir_compte(membre)
    membre.refresh_from_db()
    assert membre.a_un_compte is True
    assert membre.user.username == "zoe@example.org"  # e-mail = identifiant
    assert membre.user.first_name == "Zoé" and membre.user.last_name == "Nadal"
    assert membre.user.has_usable_password() is False  # activation requise
    assert uidb64 and token


def test_ouvrir_compte_refuse_sans_email(db):
    membre = creer_membre(prenom="Sans", nom="Mail", email="")
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)
    assert Utilisateur.objects.count() == 0


def test_ouvrir_compte_refuse_email_deja_pris(db):
    Utilisateur.objects.create_user(username="pris@example.org", password="x")
    membre = creer_membre(prenom="Doublon", nom="Mail", email="pris@example.org")
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)


def test_ouvrir_compte_refuse_si_deja_un_compte(db):
    membre = creer_membre(prenom="Deja", nom="La", email="deja@example.org")
    ouvrir_compte(membre)
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)


def test_synchroniser_compte_recopie_sans_toucher_l_identifiant(db):
    membre = creer_membre(prenom="Ava", nom="Prat", email="ava@example.org")
    ouvrir_compte(membre)
    membre.prenom, membre.nom, membre.email = "Ava", "Prade", "ava2@example.org"
    membre.save()
    synchroniser_compte(membre)
    membre.user.refresh_from_db()
    assert membre.user.last_name == "Prade"
    assert membre.user.email == "ava2@example.org"
    assert membre.user.username == "ava@example.org"  # identifiant inchangé
