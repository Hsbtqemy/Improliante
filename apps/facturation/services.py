"""Services métier du domaine « Facturation ».

`valider_facture` attribue le numéro de façon SÉQUENTIELLE, CONTINUE et SANS
TROU, à la validation (contrainte légale, cf. cahier §4). L'incrément se fait
sous verrou (`select_for_update`) dans une transaction : l'unicité est garantie
même en cas de validations concurrentes (sur PostgreSQL).

Toute transition relit la pièce SOUS VERROU avant de la contrôler : l'instance
reçue par un service peut être périmée (double clic, deux onglets ouverts).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from functools import partial
from types import SimpleNamespace

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.coeur.models import ParametresAssociation
from apps.common import instantane as fige
from apps.common import pdf

from .models import CompteurFacture, Devis, Facture, LigneFacture

logger = logging.getLogger(__name__)


class ValidationRefusee(Exception):
    """Base des refus de validation : le message s'affiche tel quel."""


class FactureDejaValidee(ValidationRefusee):
    """Levée quand on tente de (re)valider une facture qui n'est pas en brouillon."""


class FactureSansLigne(ValidationRefusee):
    """Levée quand on tente de valider une facture qui n'a aucune ligne."""


class AvoirExcessif(ValidationRefusee):
    """Levée quand un avoir annulerait plus que ce qui reste de sa facture."""


class DevisDejaFacture(Exception):
    """Levée quand on tente de transformer un devis déjà transformé en facture."""


class FactureNonAvoirable(Exception):
    """Levée quand on tente de créer un avoir sur une pièce qui ne le permet pas."""


def _euros(montant: Decimal) -> str:
    return f"{montant:.2f} €".replace(".", ",")


@transaction.atomic
def valider_facture(facture: Facture, *, date_emission: date | None = None) -> Facture:
    """Valide une facture : lui attribue un numéro et fige sa date d'émission.

    - Refuse une facture déjà validée (pas de renumérotation) ou sans ligne.
    - Refuse un avoir qui annulerait plus que ce qui reste de sa facture.
    - Numéro au format ``F{annee}-{séquence:04d}`` (série annuelle continue).
    - Le PDF est rendu dès le commit : la pièce est figée telle qu'émise, pas
      telle que seraient le client ou l'association au premier téléchargement.

    L'état contrôlé est celui RELU SOUS VERROU, jamais celui de l'instance
    reçue : deux requêtes parties du même brouillon passaient sinon toutes deux
    le contrôle, et la seconde réécrivait le numéro de la première — un numéro
    consommé que plus aucune pièce ne porte. L'instance reçue est mise à jour.
    """
    courante = Facture.objects.select_for_update().get(pk=facture.pk)
    if courante.statut != Facture.Statut.BROUILLON or courante.numero:
        raise FactureDejaValidee(
            f"La facture {courante} n'est pas en brouillon "
            f"(statut : {courante.get_statut_display().lower()})."
        )
    if not courante.lignes.exists():
        raise FactureSansLigne("Impossible de valider une facture sans ligne.")
    if courante.type_piece == Facture.TypePiece.AVOIR and courante.avoir_de_id:
        _verifier_reste_a_annuler(courante)

    jour = date_emission or timezone.localdate()

    # get_or_create couvre la 1re facture de l'année (course rare) ; on reprend
    # ensuite la ligne SOUS VERROU pour incrémenter de façon sûre.
    CompteurFacture.objects.get_or_create(annee=jour.year)
    compteur = CompteurFacture.objects.select_for_update().get(annee=jour.year)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])

    # Séquence unique partagée facture/avoir (chronologie continue) ; le préfixe
    # distingue le type de pièce (F = facture, A = avoir).
    prefixe = "A" if courante.type_piece == Facture.TypePiece.AVOIR else "F"
    courante.numero = f"{prefixe}{jour.year}-{compteur.dernier:04d}"
    courante.statut = Facture.Statut.VALIDEE
    courante.date = jour
    courante.date_validation = timezone.now()
    courante.instantane = _instantane(courante)
    champs = ["numero", "statut", "date", "date_validation", "instantane"]
    courante.save(update_fields=champs)
    for champ in champs:
        setattr(facture, champ, getattr(courante, champ))

    # Après le commit, pas dedans : un rendu raté n'annule pas un numéro
    # légalement attribué (`robust` journalise au lieu de lever).
    transaction.on_commit(partial(_figer_pdf, courante.pk), robust=True)
    return facture


def _reste_a_annuler(facture: Facture) -> Decimal:
    """TTC de la facture, diminué de ses avoirs déjà ÉMIS (montants négatifs)."""
    emis = facture.avoirs.exclude(numero=None).prefetch_related("lignes")
    return facture.total_ttc + sum((avoir.total_ttc for avoir in emis), Decimal("0.00"))


def _verifier_reste_a_annuler(avoir: Facture) -> None:
    """Lève `AvoirExcessif` si `avoir` annulerait plus que ce qui reste.

    La facture d'origine est verrouillée : deux avoirs validés au même instant
    se comptent l'un l'autre au lieu de passer chacun sur l'ancien reste."""
    origine = Facture.objects.select_for_update().get(pk=avoir.avoir_de_id)
    reste = _reste_a_annuler(origine)
    if -avoir.total_ttc > reste:
        raise AvoirExcessif(
            f"Cet avoir annulerait {_euros(-avoir.total_ttc)} TTC, alors qu'il ne reste "
            f"que {_euros(reste)} à annuler sur la facture {origine}."
        )


@transaction.atomic
def creer_avoir(facture: Facture) -> Facture:
    """Crée un avoir (brouillon) annulant une facture VALIDÉE.

    Reprend le client et les lignes de la facture avec des quantités négatives
    (montants inversés). L'avoir est ensuite validé comme une facture (numéro
    de série « A… »). Lève `FactureNonAvoirable` si la pièce n'est pas une
    facture validée, si un avoir est déjà en préparation (double clic), ou si
    ses avoirs émis l'annulent déjà entièrement.

    Un avoir PARTIEL reste possible : le brouillon se retouche avant d'être
    validé, et `valider_facture` garantit que la somme des avoirs ne dépasse
    jamais la facture."""
    facture = Facture.objects.select_for_update().get(pk=facture.pk)
    if facture.statut == Facture.Statut.BROUILLON:
        raise FactureNonAvoirable("Seule une facture validée peut faire l'objet d'un avoir.")
    if facture.type_piece == Facture.TypePiece.AVOIR:
        raise FactureNonAvoirable("Un avoir ne peut pas lui-même faire l'objet d'un avoir.")
    en_preparation = facture.avoirs.filter(numero=None).first()
    if en_preparation is not None:
        raise FactureNonAvoirable(
            f"Un avoir est déjà en préparation pour cette facture ({en_preparation}) : "
            "validez-le ou supprimez-le d'abord."
        )
    if _reste_a_annuler(facture) <= 0:
        raise FactureNonAvoirable(
            f"La facture {facture} est déjà entièrement annulée par ses avoirs."
        )

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


@transaction.atomic
def dupliquer_facture(facture: Facture) -> Facture:
    """Recopie une facture en un BROUILLON neuf, prêt à être ajusté.

    Le geste courant d'un trésorier : la même prestation revient d'une saison à
    l'autre, avec deux chiffres à changer. Le copier à la main, c'est risquer
    d'oublier une ligne.

    Ce que la copie NE reprend PAS est le cœur de la fonction, et découle de la
    règle 4 : ni le numéro, ni le statut, ni la date d'émission, ni le lien
    d'avoir. Une pièce dupliquée est un brouillon sans identité légale, qui
    recevra son propre numéro à SA validation — reprendre le numéro d'origine
    créerait un doublon dans une série qui doit rester unique et continue.

    Un avoir se duplique aussi : le résultat est un brouillon de même type,
    mais détaché de la facture annulée, car un avoir ne s'annule pas deux fois.
    """
    copie = Facture.objects.create(
        client=facture.client,
        type_piece=facture.type_piece,
        objet=facture.objet,
        mentions_legales=facture.mentions_legales,
        signataire=facture.signataire,
        # `avoir_de` volontairement omis : la copie ne rejoue pas l'annulation.
    )
    for ligne in facture.lignes.all():
        LigneFacture.objects.create(
            facture=copie,
            designation=ligne.designation,
            quantite=ligne.quantite,
            prix_unitaire_ht=ligne.prix_unitaire_ht,
            taux_tva=ligne.taux_tva,
            ordre=ligne.ordre,
        )
    return copie


def _instantane(facture: Facture) -> dict:
    """Fige émetteur, client, lignes et totaux au moment de l'émission.

    Les montants y sont figés en TEXTE : le JSON ne connaît pas le décimal, et
    passer par un flottant ferait mentir la pièce d'un centime."""
    return {
        "version": 1,
        "emetteur": fige.emetteur(ParametresAssociation.load()),
        "client": {
            champ: getattr(facture.client, champ)
            for champ in ("nom", "adresse", "code_postal", "ville", "siret", "numero_tva")
        },
        "signataire": fige.signataire(facture.signataire),
        "lignes": [
            {
                "designation": ligne.designation,
                "quantite": str(ligne.quantite),
                "prix_unitaire_ht": str(ligne.prix_unitaire_ht),
                "taux_tva": str(ligne.taux_tva),
                "total_ht": str(ligne.total_ht),
            }
            for ligne in facture.lignes.all()
        ],
        "totaux": {
            "total_ht": str(facture.total_ht),
            "total_tva": str(facture.total_tva),
            "total_ttc": str(facture.total_ttc),
        },
    }


def _facture_figee(facture: Facture) -> SimpleNamespace:
    """La facture telle qu'elle a été émise, sous la forme qu'attend le gabarit."""
    instant = facture.instantane
    return SimpleNamespace(
        numero=facture.numero,
        date=facture.date,
        date_echeance=facture.date_echeance,
        objet=facture.objet,
        type_piece=facture.type_piece,
        mentions_legales=facture.mentions_legales,
        client=fige.en_objet(instant["client"]),
        signataire=fige.en_objet(instant["signataire"]),
        avoir_de=SimpleNamespace(numero=facture.avoir_de.numero) if facture.avoir_de_id else None,
        lignes=SimpleNamespace(all=[fige.en_objet(ligne) for ligne in instant["lignes"]]),
        **instant["totaux"],
    )


def pdf_de_facture(facture: Facture, *, apercu: bool = False) -> bytes:
    """Rend le PDF d'une facture.

    Une pièce ÉMISE est rendue depuis son INSTANTANÉ : si le PDF archivé
    disparaît, on le reconstruit tel qu'il a été émis — pas avec le nom que
    l'association porte aujourd'hui, ni l'adresse que le client a depuis.
    `apercu=True` fait l'inverse, et c'est son rôle : un brouillon filigrané
    « sans valeur », rendu à partir des données vivantes, pour vérifier avant
    d'émettre."""
    if not apercu and facture.instantane:
        contexte = {
            "facture": _facture_figee(facture),
            "asso": fige.en_objet(facture.instantane["emetteur"]),
            "apercu": False,
        }
    else:
        contexte = {"facture": facture, "asso": ParametresAssociation.load(), "apercu": apercu}
    return pdf.html_vers_pdf(render_to_string("facture/facture.html", contexte))


@transaction.atomic
def assurer_pdf_facture(facture: Facture) -> None:
    """Garantit le PDF d'une facture VALIDÉE dans le stockage privé.

    Rendu une seule fois puis conservé (immuabilité du document légal) —
    normalement dès la validation (`_figer_pdf`) ; ce rendu à la demande n'est
    plus qu'un repli, quand le moteur PDF manquait à ce moment-là. Ne rend rien
    pour un brouillon (pas de numéro : pas de PDF légal).

    L'absence de fichier est revérifiée sous verrou : deux premiers
    téléchargements simultanés rendaient sinon deux fois, et le second
    remplaçait le PDF archivé. L'instance reçue récupère le fichier."""
    if facture.fichier or facture.statut == Facture.Statut.BROUILLON:
        return
    courante = Facture.objects.select_for_update().get(pk=facture.pk)
    if not courante.fichier:
        octets = pdf_de_facture(courante)
        courante.fichier.save(f"facture-{courante.numero}.pdf", ContentFile(octets), save=False)
        courante.save(update_fields=["fichier"])
    facture.refresh_from_db(fields=["fichier"])


def _figer_pdf(facture_pk: int) -> None:
    """Rend et archive le PDF d'une facture qui vient d'être émise.

    Sans moteur PDF (poste Windows sans Pango), la pièce retombe sur le rendu
    au premier téléchargement : moins sûr, mais le numéro reste valable."""
    try:
        assurer_pdf_facture(Facture.objects.get(pk=facture_pk))
    except pdf.RenduPDFIndisponible as exc:
        logger.warning("PDF de la facture #%s non figé à l'émission : %s", facture_pk, exc)


# --- Devis ------------------------------------------------------------------


def numeroter_devis(devis: Devis) -> None:
    """Attribue un numéro au devis s'il n'en a pas encore.

    Série annuelle « D{annee}-{seq:04d} ». Contrairement aux factures, le devis
    n'a PAS de contrainte légale de continuité : un trou (devis supprimé) est
    toléré. On se fonde sur le plus grand numéro déjà attribué dans l'année
    (et non sur un `count()`) : supprimer un devis au milieu de la série ne fait
    pas réattribuer un numéro encore porté par un autre — ce qui créerait un
    doublon. Limite : supprimer le DERNIER devis de l'année libère son numéro,
    que le suivant reprendra. La concurrence (deux devis créés exactement en
    même temps) n'est pas verrouillée non plus : acceptable pour un devis, qui
    n'a pas la criticité légale d'une facture."""
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
    Lève `DevisDejaFacture` si le devis a déjà été transformé — statut relu sous
    verrou, pour qu'un double clic ne crée pas deux factures."""
    courant = Devis.objects.select_for_update().get(pk=devis.pk)
    if courant.statut == Devis.Statut.FACTURE:
        raise DevisDejaFacture(
            f"Le devis {courant.numero or courant.pk} a déjà été transformé en facture."
        )
    facture = Facture.objects.create(
        client=courant.client,
        devis_origine=courant,
        objet=courant.objet,
    )
    for ligne in courant.lignes.all():
        LigneFacture.objects.create(
            facture=facture,
            designation=ligne.designation,
            quantite=ligne.quantite,
            prix_unitaire_ht=ligne.prix_unitaire_ht,
            taux_tva=ligne.taux_tva,
            ordre=ligne.ordre,
        )
    courant.statut = Devis.Statut.FACTURE
    courant.save(update_fields=["statut"])
    devis.statut = courant.statut
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
