"""Services métier du domaine « Facturation ».

`valider_facture` attribue le numéro de façon SÉQUENTIELLE, CONTINUE et SANS
TROU, à la validation (contrainte légale, cf. cahier §4). L'incrément se fait
sous verrou (`select_for_update`) dans une transaction : l'unicité est garantie
même en cas de validations concurrentes (sur PostgreSQL).
"""

from __future__ import annotations

from datetime import date

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.coeur.models import ParametresAssociation
from apps.common import pdf

from .models import CompteurFacture, Devis, Facture, LigneFacture


class FactureDejaValidee(Exception):
    """Levée quand on tente de (re)valider une facture qui n'est pas en brouillon."""


class DevisDejaFacture(Exception):
    """Levée quand on tente de transformer un devis déjà transformé en facture."""


@transaction.atomic
def valider_facture(facture: Facture, *, date_emission: date | None = None) -> Facture:
    """Valide une facture : lui attribue un numéro et fige sa date d'émission.

    - Refuse une facture déjà validée (pas de renumérotation).
    - Numéro au format ``F{annee}-{séquence:04d}`` (série annuelle continue).
    """
    if facture.statut != Facture.Statut.BROUILLON or facture.numero:
        raise FactureDejaValidee(
            f"La facture #{facture.pk} n'est pas en brouillon (statut : {facture.statut})."
        )

    jour = date_emission or timezone.localdate()

    # get_or_create couvre la 1re facture de l'année (course rare) ; on reprend
    # ensuite la ligne SOUS VERROU pour incrémenter de façon sûre.
    CompteurFacture.objects.get_or_create(annee=jour.year)
    compteur = CompteurFacture.objects.select_for_update().get(annee=jour.year)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])

    facture.numero = f"F{jour.year}-{compteur.dernier:04d}"
    facture.statut = Facture.Statut.VALIDEE
    facture.date = jour
    facture.date_validation = timezone.now()
    facture.save(update_fields=["numero", "statut", "date", "date_validation"])
    return facture


def pdf_de_facture(facture: Facture, *, apercu: bool = False) -> bytes:
    """Rend le PDF d'une facture. `apercu=True` produit un brouillon filigrané
    « sans valeur » (dry-run avant validation), sans numéro légal."""
    html = render_to_string(
        "facture/facture.html",
        {"facture": facture, "asso": ParametresAssociation.load(), "apercu": apercu},
    )
    return pdf.html_vers_pdf(html)


def assurer_pdf_facture(facture: Facture) -> None:
    """Garantit le PDF d'une facture VALIDÉE dans le stockage privé.

    Rendu une seule fois puis mis en cache (immuabilité du document légal).
    Ne rend rien pour un brouillon (pas de numéro : pas de PDF légal)."""
    if facture.fichier or facture.statut == Facture.Statut.BROUILLON:
        return
    octets = pdf_de_facture(facture)
    facture.fichier.save(f"facture-{facture.numero}.pdf", ContentFile(octets), save=True)


# --- Devis ------------------------------------------------------------------


def numeroter_devis(devis: Devis) -> None:
    """Attribue un numéro au devis s'il n'en a pas encore.

    Série annuelle « D{annee}-{seq:04d} ». Contrairement aux factures, le devis
    n'a PAS de contrainte légale de continuité : un trou (devis supprimé) est
    sans conséquence, on ne verrouille donc pas l'attribution."""
    if devis.numero:
        return
    annee = (devis.date or timezone.localdate()).year
    seq = Devis.objects.filter(date__year=annee).exclude(pk=devis.pk).count() + 1
    devis.numero = f"D{annee}-{seq:04d}"
    devis.save(update_fields=["numero"])


def pdf_de_devis(devis: Devis) -> bytes:
    """Rend le PDF d'un devis à la volée (pas de cache : le devis évolue tant
    qu'il n'est pas accepté / transformé)."""
    html = render_to_string(
        "devis/devis.html",
        {"devis": devis, "asso": ParametresAssociation.load()},
    )
    return pdf.html_vers_pdf(html)


@transaction.atomic
def transformer_en_facture(devis: Devis) -> Facture:
    """Crée une facture brouillon à partir d'un devis (client + lignes copiés).

    Marque le devis comme « Facturé » et relie la facture à son devis d'origine.
    Lève `DevisDejaFacture` si le devis a déjà été transformé."""
    if devis.statut == Devis.Statut.FACTURE:
        raise DevisDejaFacture(
            f"Le devis {devis.numero or devis.pk} a déjà été transformé en facture."
        )
    facture = Facture.objects.create(
        client=devis.client,
        devis_origine=devis,
        objet=devis.objet,
    )
    for ligne in devis.lignes.all():
        LigneFacture.objects.create(
            facture=facture,
            designation=ligne.designation,
            quantite=ligne.quantite,
            prix_unitaire_ht=ligne.prix_unitaire_ht,
            taux_tva=ligne.taux_tva,
            ordre=ligne.ordre,
        )
    devis.statut = Devis.Statut.FACTURE
    devis.save(update_fields=["statut"])
    return facture
