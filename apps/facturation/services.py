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

from .models import CompteurFacture, Facture


class FactureDejaValidee(Exception):
    """Levée quand on tente de (re)valider une facture qui n'est pas en brouillon."""


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


def assurer_pdf_facture(facture: Facture) -> None:
    """Garantit le PDF d'une facture VALIDÉE dans le stockage privé.

    Rendu une seule fois puis mis en cache (immuabilité du document légal).
    Ne rend rien pour un brouillon (pas de numéro : pas de PDF légal)."""
    if facture.fichier or facture.statut == Facture.Statut.BROUILLON:
        return
    html = render_to_string(
        "facture/facture.html",
        {"facture": facture, "asso": ParametresAssociation.load()},
    )
    octets = pdf.html_vers_pdf(html)
    facture.fichier.save(f"facture-{facture.numero}.pdf", ContentFile(octets), save=True)
