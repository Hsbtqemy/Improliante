"""Services métier du domaine « Budget » — émission des reçus fiscaux.

`emettre_recu` attribue un numéro SÉQUENTIEL, CONTINU et SANS TROU (contrainte
légale identique aux factures), sous verrou dans une transaction, et fige un
snapshot des données. Le PDF Cerfa est rendu paresseusement (WeasyPrint) au
premier téléchargement puis mis en cache — la création ne dépend pas de la
présence de WeasyPrint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.coeur.models import ParametresAssociation
from apps.common import pdf

from .models import CompteurRecu, RecuFiscal


@transaction.atomic
def emettre_recu(
    *,
    type_versement: str,
    montant: Decimal,
    date_versement: date,
    donateur_nom: str,
    donateur_adresse: str = "",
    donateur_code_postal: str = "",
    donateur_ville: str = "",
    forme: str = RecuFiscal.Forme.NUMERAIRE,
    membre=None,
    adhesion=None,
    transaction_source=None,
    emis_par=None,
    signataire=None,
    date_emission: date | None = None,
) -> RecuFiscal:
    """Émet un reçu fiscal : numéro annuel continu + snapshot des données.

    Numéro au format ``R{annee}-{séquence:04d}``.
    """
    jour = date_emission or timezone.localdate()

    # get_or_create couvre le 1er reçu de l'année ; on reprend la ligne SOUS
    # VERROU pour incrémenter de façon sûre (unicité garantie sur PostgreSQL).
    CompteurRecu.objects.get_or_create(annee=jour.year)
    compteur = CompteurRecu.objects.select_for_update().get(annee=jour.year)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])

    return RecuFiscal.objects.create(
        numero=f"R{jour.year}-{compteur.dernier:04d}",
        date_emission=jour,
        type_versement=type_versement,
        forme=forme,
        montant=montant,
        date_versement=date_versement,
        donateur_nom=donateur_nom,
        donateur_adresse=donateur_adresse,
        donateur_code_postal=donateur_code_postal,
        donateur_ville=donateur_ville,
        membre=membre,
        adhesion=adhesion,
        transaction=transaction_source,
        emis_par=emis_par,
        signataire=signataire,
    )


def donnees_depuis_adhesion(adhesion) -> dict:
    """Valeurs initiales pour pré-remplir le formulaire d'émission depuis une
    adhésion (le bureau complète ensuite l'adresse, absente du modèle Membre)."""
    return {
        "type_versement": RecuFiscal.TypeVersement.COTISATION,
        "montant": adhesion.montant_verse,
        "date_versement": adhesion.date or timezone.localdate(),
        "donateur_nom": str(adhesion.membre),
    }


def pdf_de_recu(recu: RecuFiscal, *, apercu: bool = False) -> bytes:
    """Rend le PDF Cerfa d'un reçu. `apercu=True` produit un document filigrané
    « sans valeur » pour prévisualiser AVANT émission (reçu non enregistré)."""
    html = render_to_string(
        "recu/cerfa.html",
        {"recu": recu, "asso": ParametresAssociation.load(), "apercu": apercu},
    )
    return pdf.html_vers_pdf(html)


def assurer_pdf_recu(recu: RecuFiscal) -> None:
    """Garantit que le PDF Cerfa du reçu existe dans le stockage privé.

    Rendu une seule fois : une fois le fichier en cache, il n'est plus
    régénéré (immuabilité du document légal)."""
    if recu.fichier:
        return
    octets = pdf_de_recu(recu)
    recu.fichier.save(f"recu-{recu.numero}.pdf", ContentFile(octets), save=True)
