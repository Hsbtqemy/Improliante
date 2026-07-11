"""Services métier du domaine « Facturation ».

`valider_facture` attribue le numéro de façon SÉQUENTIELLE, CONTINUE et SANS
TROU, à la validation (contrainte légale, cf. cahier §4). L'incrément se fait
sous verrou (`select_for_update`) dans une transaction : l'unicité est garantie
même en cas de validations concurrentes (sur PostgreSQL).
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

from .models import CompteurFacture, Devis, Facture, LigneFacture


class FactureDejaValidee(Exception):
    """Levée quand on tente de (re)valider une facture qui n'est pas en brouillon."""


class DevisDejaFacture(Exception):
    """Levée quand on tente de transformer un devis déjà transformé en facture."""


class FactureNonAvoirable(Exception):
    """Levée quand on tente de créer un avoir sur une pièce qui ne le permet pas."""


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

    # Séquence unique partagée facture/avoir (chronologie continue) ; le préfixe
    # distingue le type de pièce (F = facture, A = avoir).
    prefixe = "A" if facture.type_piece == Facture.TypePiece.AVOIR else "F"
    facture.numero = f"{prefixe}{jour.year}-{compteur.dernier:04d}"
    facture.statut = Facture.Statut.VALIDEE
    facture.date = jour
    facture.date_validation = timezone.now()
    facture.save(update_fields=["numero", "statut", "date", "date_validation"])
    return facture


@transaction.atomic
def creer_avoir(facture: Facture) -> Facture:
    """Crée un avoir (brouillon) annulant une facture VALIDÉE.

    Reprend le client et les lignes de la facture avec des quantités négatives
    (montants inversés). L'avoir est ensuite validé comme une facture (numéro
    de série « A… »). Lève `FactureNonAvoirable` si la pièce n'est pas une
    facture validée."""
    if facture.statut == Facture.Statut.BROUILLON:
        raise FactureNonAvoirable("Seule une facture validée peut faire l'objet d'un avoir.")
    if facture.type_piece == Facture.TypePiece.AVOIR:
        raise FactureNonAvoirable("Un avoir ne peut pas lui-même faire l'objet d'un avoir.")

    avoir = Facture.objects.create(
        client=facture.client,
        type_piece=Facture.TypePiece.AVOIR,
        avoir_de=facture,
        objet=f"Avoir sur facture {facture.numero}",
    )
    for ligne in facture.lignes.all():
        LigneFacture.objects.create(
            facture=avoir,
            designation=ligne.designation,
            quantite=-ligne.quantite,  # montants inversés
            prix_unitaire_ht=ligne.prix_unitaire_ht,
            taux_tva=ligne.taux_tva,
            ordre=ligne.ordre,
        )
    return avoir


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
    toléré. On se fonde sur le plus grand numéro déjà attribué dans l'année
    (et non sur un `count()`) pour ne jamais réutiliser un numéro après une
    suppression — ce qui créerait un doublon. La concurrence (deux devis créés
    exactement en même temps) n'est pas verrouillée : acceptable pour un devis,
    qui n'a pas la criticité légale d'une facture."""
    if devis.numero:
        return
    annee = (devis.date or timezone.localdate()).year
    prefixe = f"D{annee}-"
    dernier = 0
    for numero in Devis.objects.filter(numero__startswith=prefixe).values_list("numero", flat=True):
        try:
            dernier = max(dernier, int(numero.removeprefix(prefixe)))
        except ValueError:
            continue  # numéro hors format : ignoré
    devis.numero = f"{prefixe}{dernier + 1:04d}"
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


def resume_facturation() -> dict:
    """Chiffres clés de la facturation pour le hub Finances.

    Les compteurs sont calculés en base ; le montant « en attente de paiement »
    est sommé en Python sur les seules factures validées (`total_ttc` dérive des
    lignes, préchargées ici)."""
    factures = Facture.objects.filter(type_piece=Facture.TypePiece.FACTURE)
    en_attente = list(factures.filter(statut=Facture.Statut.VALIDEE).prefetch_related("lignes"))
    return {
        "factures_a_valider": factures.filter(statut=Facture.Statut.BROUILLON).count(),
        "factures_payees": factures.filter(statut=Facture.Statut.PAYEE).count(),
        "en_attente_nb": len(en_attente),
        "en_attente_montant": sum((f.total_ttc for f in en_attente), Decimal("0.00")),
        "devis_a_suivre": Devis.objects.filter(
            statut__in=[Devis.Statut.ENVOYE, Devis.Statut.ACCEPTE]
        ).count(),
    }
