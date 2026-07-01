"""Tests de la numérotation des factures (zone à risque, cf. cahier §4).

Note : ces tests tournent sur SQLite ; `select_for_update` y est un no-op, donc
ils valident les RÈGLES fonctionnelles (séquentielle, continue, sans trou, à la
validation), pas la sûreté concurrentielle — celle-ci repose sur PostgreSQL.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.facturation.services import (
    DevisDejaFacture,
    FactureDejaValidee,
    FactureNonAvoirable,
    creer_avoir,
    numeroter_devis,
    transformer_en_facture,
    valider_facture,
)


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


def test_reinit_factures_remet_la_numerotation_a_zero(client_facture, settings):
    # La commande refuse de tourner hors DEBUG (protection prod) ; pytest force
    # DEBUG=False, on le réactive donc explicitement pour ce test.
    settings.DEBUG = True

    f = Facture.objects.create(client=client_facture)
    valider_facture(f, date_emission=date(2026, 3, 1))
    assert Facture.objects.count() == 1

    call_command("reinit_factures", "--yes")
    assert Facture.objects.count() == 0

    # La numérotation repart bien à 0001.
    f2 = Facture.objects.create(client=client_facture)
    valider_facture(f2, date_emission=date(2026, 3, 1))
    f2.refresh_from_db()
    assert f2.numero == "F2026-0001"


# --- Devis : numérotation souple + transformation en facture ---------------


def test_numeroter_devis_attribue_un_numero(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    numeroter_devis(devis)
    assert devis.numero == "D2026-0001"


def test_numeroter_devis_ne_reecrit_pas_un_numero_existant(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1), numero="D2026-0042")
    numeroter_devis(devis)
    assert devis.numero == "D2026-0042"


def test_transformer_en_facture_copie_client_et_lignes(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1), objet="Spectacle")
    LigneDevis.objects.create(
        devis=devis,
        designation="Représentation",
        quantite=2,
        prix_unitaire_ht=Decimal("100"),
        taux_tva=Decimal("20"),
    )
    facture = transformer_en_facture(devis)
    devis.refresh_from_db()
    assert devis.statut == Devis.Statut.FACTURE
    assert facture.client == client_facture
    assert facture.devis_origine == devis
    assert facture.objet == "Spectacle"
    assert facture.lignes.count() == 1
    assert facture.total_ttc == Decimal("240.00")  # 2 × 100 + 20 %


def test_transformer_un_devis_deja_facture_leve(client_facture):
    devis = Devis.objects.create(
        client=client_facture, date=date(2026, 3, 1), statut=Devis.Statut.FACTURE
    )
    with pytest.raises(DevisDejaFacture):
        transformer_en_facture(devis)


# --- Avoir : annulation d'une facture validée ------------------------------


def _facture_validee(client_facture, **ligne):
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture,
        designation=ligne.get("designation", "Prestation"),
        quantite=ligne.get("quantite", 2),
        prix_unitaire_ht=ligne.get("prix_unitaire_ht", Decimal("100")),
        taux_tva=ligne.get("taux_tva", Decimal("20")),
    )
    valider_facture(facture, date_emission=date(2026, 3, 1))
    return facture


def test_creer_avoir_reprend_les_lignes_inversees(client_facture):
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    assert avoir.type_piece == Facture.TypePiece.AVOIR
    assert avoir.avoir_de == facture
    assert avoir.statut == Facture.Statut.BROUILLON
    assert avoir.lignes.count() == 1
    assert avoir.total_ttc == Decimal("-240.00")  # 2×100 +20 %, inversé


def test_avoir_valide_prend_un_numero_de_serie_a_continue(client_facture):
    facture = _facture_validee(client_facture)  # F2026-0001
    avoir = creer_avoir(facture)
    valider_facture(avoir, date_emission=date(2026, 3, 1))
    avoir.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert avoir.numero == "A2026-0002"  # séquence partagée, continue


def test_creer_avoir_sur_brouillon_refuse(client_facture):
    facture = Facture.objects.create(client=client_facture)  # brouillon
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(facture)


def test_creer_avoir_sur_avoir_refuse(client_facture):
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    valider_facture(avoir, date_emission=date(2026, 3, 1))
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(avoir)
