"""Tests des calculs de gouvernance (zone à risque, cf. cahier §8)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.budget.models import Adhesion, Saison
from apps.coeur.models import Membre, Utilisateur
from apps.gouvernance.models import (
    ParametresGouvernance,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
)
from apps.gouvernance.services import (
    calcul_quorum,
    mandataires_en_exces,
    preremplir_droit_de_vote,
    resultat_resolution,
)


@pytest.fixture
def params(db):
    return ParametresGouvernance.load()


@pytest.fixture
def make_membre(db):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        user = Utilisateur.objects.create(username=f"membre{compteur['n']}")
        return Membre.objects.create(user=user)

    return _make


def _reunion(type_reunion=Reunion.TypeReunion.AG_ORDINAIRE):
    return Reunion.objects.create(titre="Réunion", type_reunion=type_reunion)


def _presence(reunion, membre, statut, peut_voter=True):
    return Presence.objects.create(
        reunion=reunion, membre=membre, statut=statut, peut_voter=peut_voter
    )


def _resolution(type_majorite, pour, contre, abstention=0):
    return Resolution.objects.create(
        reunion=_reunion(),
        intitule="R",
        type_majorite=type_majorite,
        nombre_pour=pour,
        nombre_contre=contre,
        nombre_abstention=abstention,
    )


# --- Quorum ---------------------------------------------------------------


def test_quorum_atteint(params, make_membre):
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    membres = [make_membre() for _ in range(4)]
    _presence(reunion, membres[0], Presence.Statut.PRESENT)
    _presence(reunion, membres[1], Presence.Statut.REPRESENTE)
    _presence(reunion, membres[2], Presence.Statut.ABSENT)
    _presence(reunion, membres[3], Presence.Statut.EXCUSE)

    resultat = calcul_quorum(reunion)
    assert resultat.electorat == 4
    assert resultat.presents_representes == 2
    assert resultat.atteint is True  # 2/4 = 0.5 >= 0.5


def test_quorum_non_atteint(params, make_membre):
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    membres = [make_membre() for _ in range(4)]
    _presence(reunion, membres[0], Presence.Statut.PRESENT)
    for membre in membres[1:]:
        _presence(reunion, membre, Presence.Statut.ABSENT)

    resultat = calcul_quorum(reunion)
    assert resultat.presents_representes == 1
    assert resultat.atteint is False  # 1/4 < 0.5


def test_quorum_bureau_non_applicable(params):
    resultat = calcul_quorum(_reunion(Reunion.TypeReunion.BUREAU))
    assert resultat.applicable is False
    assert resultat.atteint is True


def test_quorum_electorat_vide(params):
    resultat = calcul_quorum(_reunion())
    assert resultat.electorat == 0
    assert resultat.atteint is False


# --- Adoption des résolutions --------------------------------------------


def test_majorite_simple_adoptee(params):
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=3, contre=2, abstention=1)
    resultat = resultat_resolution(res)
    assert resultat.base == 5  # exprimés (défaut)
    assert resultat.adoptee is True  # 3/5 > 0.5


def test_majorite_simple_egalite_rejetee(params):
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=2, contre=2)
    assert resultat_resolution(res).adoptee is False  # 2/4 = 0.5, pas > 0.5


def test_majorite_qualifiee_deux_tiers(params):
    adoptee = _resolution(Resolution.TypeMajorite.QUALIFIEE, pour=2, contre=1)
    assert resultat_resolution(adoptee).adoptee is True  # 2/3 -> 0.667 >= 0.667
    rejetee = _resolution(Resolution.TypeMajorite.QUALIFIEE, pour=3, contre=2)
    assert resultat_resolution(rejetee).adoptee is False  # 3/5 = 0.6 < 0.667


def test_unanimite(params):
    ok = _resolution(Resolution.TypeMajorite.UNANIMITE, pour=5, contre=0, abstention=1)
    assert resultat_resolution(ok).adoptee is True
    ko = _resolution(Resolution.TypeMajorite.UNANIMITE, pour=5, contre=1)
    assert resultat_resolution(ko).adoptee is False


def test_base_presents_change_le_resultat(params):
    params.base_majorite = ParametresGouvernance.BaseMajorite.PRESENTS
    params.save()
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=3, contre=2, abstention=2)
    resultat = resultat_resolution(res)
    assert resultat.base == 7  # abstentions comprises
    assert resultat.adoptee is False  # 3/7 < 0.5 (en exprimés, 3/5 serait adopté)


# --- Pouvoirs -------------------------------------------------------------


def test_mandataires_en_exces(params, make_membre):
    params.max_pouvoirs_par_personne = 2
    params.save()
    reunion = _reunion()
    mandataire = make_membre()
    for _ in range(3):
        Pouvoir.objects.create(reunion=reunion, mandant=make_membre(), mandataire=mandataire)

    assert mandataires_en_exces(reunion) == {mandataire.pk: 3}


def test_pouvoirs_conformes(params, make_membre):
    params.max_pouvoirs_par_personne = 2
    params.save()
    reunion = _reunion()
    mandataire = make_membre()
    for _ in range(2):
        Pouvoir.objects.create(reunion=reunion, mandant=make_membre(), mandataire=mandataire)

    assert mandataires_en_exces(reunion) == {}


# --- Pré-remplissage du droit de vote -------------------------------------


def test_prerempli_vote_ouvert_a_tous_si_non_reserve(params, make_membre):
    params.vote_reserve_aux_membres_a_jour = False
    params.save()
    reunion = _reunion()
    presences = [
        _presence(reunion, make_membre(), Presence.Statut.PRESENT, peut_voter=False)
        for _ in range(2)
    ]

    assert preremplir_droit_de_vote(reunion) == 2
    for presence in presences:
        presence.refresh_from_db()
        assert presence.peut_voter is True


def test_prerempli_reserve_aux_membres_a_jour(params, make_membre):
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    saison = Saison.objects.create(nom="2025-2026")
    reunion = _reunion()
    membre_a_jour = make_membre()
    membre_pas_a_jour = make_membre()
    Adhesion.objects.create(membre=membre_a_jour, saison=saison, statut=Adhesion.Statut.PAYEE)
    Adhesion.objects.create(
        membre=membre_pas_a_jour, saison=saison, statut=Adhesion.Statut.EN_ATTENTE
    )
    p_ok = _presence(reunion, membre_a_jour, Presence.Statut.PRESENT, peut_voter=False)
    p_ko = _presence(reunion, membre_pas_a_jour, Presence.Statut.PRESENT, peut_voter=True)

    preremplir_droit_de_vote(reunion, saison)

    p_ok.refresh_from_db()
    p_ko.refresh_from_db()
    assert p_ok.peut_voter is True
    assert p_ko.peut_voter is False


def test_prerempli_reserve_sans_saison_leve_erreur(params):
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    with pytest.raises(ValueError):
        preremplir_droit_de_vote(_reunion())
