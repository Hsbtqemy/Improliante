"""Tests de la numérotation des factures (zone à risque, cf. cahier §4).

Note : ces tests tournent sur SQLite ; `select_for_update` y est un no-op, donc
ils valident les RÈGLES fonctionnelles (séquentielle, continue, sans trou, à la
validation), pas la sûreté concurrentielle — celle-ci repose sur PostgreSQL.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.facturation.models import Client, Facture
from apps.facturation.services import FactureDejaValidee, valider_facture


@pytest.fixture
def client_facture(db):
    return Client.objects.create(nom="Association X")


def test_brouillon_sans_numero(client_facture):
    facture = Facture.objects.create(client=client_facture)
    assert facture.numero is None
    assert facture.statut == Facture.Statut.BROUILLON
    assert facture.date is None


def test_validation_attribue_numero_statut_et_date(client_facture):
    facture = Facture.objects.create(client=client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    facture.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert facture.statut == Facture.Statut.VALIDEE
    assert facture.date == date(2026, 3, 1)
    assert facture.date_validation is not None


def test_sequence_continue_sans_trou(client_facture):
    numeros = []
    for _ in range(3):
        f = Facture.objects.create(client=client_facture)
        valider_facture(f, date_emission=date(2026, 3, 1))
        f.refresh_from_db()
        numeros.append(f.numero)
    assert numeros == ["F2026-0001", "F2026-0002", "F2026-0003"]


def test_revalidation_interdite(client_facture):
    facture = Facture.objects.create(client=client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    with pytest.raises(FactureDejaValidee):
        valider_facture(facture)


def test_serie_annuelle_independante(client_facture):
    f2026 = Facture.objects.create(client=client_facture)
    valider_facture(f2026, date_emission=date(2026, 12, 31))
    f2027 = Facture.objects.create(client=client_facture)
    valider_facture(f2027, date_emission=date(2027, 1, 1))
    f2026.refresh_from_db()
    f2027.refresh_from_db()
    assert f2026.numero == "F2026-0001"
    assert f2027.numero == "F2027-0001"
