"""Tests du domaine budget : émission des reçus fiscaux.

Le rendu PDF (WeasyPrint) est systématiquement remplacé par un faux moteur :
les tests valident la numérotation, le snapshot et la mise en cache, pas la
mise en page PDF.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.budget.models import Adhesion, RecuFiscal, Saison
from apps.budget.services import (
    assurer_pdf_recu,
    donnees_depuis_adhesion,
    emettre_recu,
    pdf_de_recu,
)
from apps.coeur.models import Membre, ParametresAssociation, Signataire, Utilisateur


def _membre(username="alice"):
    user = Utilisateur.objects.create_user(username=username, password="x")
    return Membre.objects.create(user=user)


def _emettre(**extra):
    donnees = {
        "type_versement": RecuFiscal.TypeVersement.DON,
        "montant": Decimal("50.00"),
        "date_versement": date(2026, 3, 1),
        "donateur_nom": "Jean Dupont",
    }
    donnees.update(extra)
    return emettre_recu(**donnees)


def test_emettre_recu_numerote_sans_trou(db):
    r1 = _emettre(date_emission=date(2026, 5, 1))
    r2 = _emettre(date_emission=date(2026, 6, 1))
    assert r1.numero == "R2026-0001"
    assert r2.numero == "R2026-0002"


def test_numerotation_repart_a_chaque_annee(db):
    r2026 = _emettre(date_emission=date(2026, 12, 31))
    r2027 = _emettre(date_emission=date(2027, 1, 1))
    assert r2026.numero == "R2026-0001"
    assert r2027.numero == "R2027-0001"


def test_emettre_recu_fige_le_snapshot(db):
    recu = _emettre(montant=Decimal("120.00"), donateur_nom="Marie Martin")
    assert recu.montant == Decimal("120.00")
    assert recu.donateur_nom == "Marie Martin"
    assert recu.type_versement == RecuFiscal.TypeVersement.DON


def test_donnees_depuis_adhesion(db):
    membre = _membre()
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(
        membre=membre,
        saison=saison,
        statut=Adhesion.Statut.PAYEE,
        montant_verse=Decimal("30.00"),
        date=date(2025, 9, 15),
    )
    donnees = donnees_depuis_adhesion(adhesion)
    assert donnees["montant"] == Decimal("30.00")
    assert donnees["type_versement"] == RecuFiscal.TypeVersement.COTISATION
    assert donnees["date_versement"] == date(2025, 9, 15)
    assert str(membre) in donnees["donateur_nom"]


def test_assurer_pdf_rend_une_seule_fois(db, monkeypatch):
    appels = []

    def faux_rendu(html, *, base_url=None):
        appels.append(html)
        return b"%PDF-1.4 faux"

    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", faux_rendu)

    recu = _emettre()
    assurer_pdf_recu(recu)
    assert recu.fichier  # le PDF a été créé et mis en cache
    assurer_pdf_recu(recu)  # 2e appel : le fichier existe déjà, pas de re-rendu
    assert len(appels) == 1
    assert recu.fichier.open("rb").read().startswith(b"%PDF")


def test_cerfa_utilise_le_signataire_choisi(db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    sig = Signataire.objects.create(nom="Alice Martin", qualite="Présidente")
    recu = _emettre(signataire=sig)
    html = pdf_de_recu(recu).decode()
    assert "Alice Martin" in html


def test_cerfa_retombe_sur_le_signataire_des_parametres(db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    params = ParametresAssociation.load()
    params.signataire_nom = "Bureau Test"
    params.signataire_qualite = "Trésorier"
    params.save()
    recu = _emettre()  # sans signataire choisi
    html = pdf_de_recu(recu).decode()
    assert "Bureau Test" in html
