"""Services métier du domaine « Budget » — émission des reçus fiscaux.

`emettre_recu` attribue un numéro SÉQUENTIEL, CONTINU et SANS TROU (contrainte
légale identique aux factures), sous verrou dans une transaction, et fige un
snapshot des données. Le PDF Cerfa est rendu dès le commit de l'émission : le
bénéficiaire et le signataire sont lus au rendu, et une pièce produite plus tard
raconterait l'association d'aujourd'hui, pas celle de l'émission. Sans moteur
PDF, le rendu retombe sur le premier téléchargement — le numéro, lui, reste
attribué.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from functools import partial
from types import SimpleNamespace

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from apps.coeur.models import ParametresAssociation
from apps.common import instantane as fige
from apps.common import pdf

from .models import Adhesion, CompteurRecu, RecuFiscal, SoldeTresorerie, Transaction

logger = logging.getLogger(__name__)


class RecuDejaEmis(Exception):
    """Levée quand le versement visé a déjà donné lieu à un reçu Cerfa."""


class AdhesionAvecRecu(Exception):
    """Levée quand on tente de supprimer une adhésion dont un reçu a été émis."""


@transaction.atomic
def supprimer_adhesion(adhesion) -> None:
    """Supprime une adhésion — sauf si un reçu fiscal en est issu.

    Un reçu émis est une pièce légale, et le dépôt l'a déjà tranché pour
    lui-même : `RecuFiscalAdmin` refuse qu'on le retouche, « pas même ses
    rattachements comptables, qui changent ce que le registre raconte ».
    Supprimer l'adhésion faisait exactement cela par l'autre bout — les liens
    sont en `SET_NULL`, donc le reçu survit et son PDF reste reproductible, mais
    il ne dit plus quelle cotisation il couvre. Rien ne le signalait : le seul
    garde-fou était un `confirm()` de navigateur qui ne parlait pas des reçus.

    Les transactions liées, elles, restent simplement détachées : une écriture
    budgétaire est interne à l'association, elle n'est partie chez personne.
    Décision de l'association du 13 septembre 2026.

    L'adhésion est relue SOUS VERROU, le même que prend `emettre_recu` : sans
    lui, un reçu émis au même instant naîtrait orphelin, la suppression ayant
    lu la table des reçus juste avant qu'il n'y entre."""
    courante = Adhesion.objects.select_for_update().get(pk=adhesion.pk)
    numeros = list(courante.recus_fiscaux.values_list("numero", flat=True))
    if numeros:
        raise AdhesionAvecRecu(
            f"Un reçu fiscal a été émis pour cette adhésion ({', '.join(numeros)}) : "
            "elle ne se supprime plus. Un reçu ne change pas de rattachement — "
            "corrigez l'adhésion plutôt que de l'effacer."
        )
    courante.delete()


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

    Un versement ne donne lieu qu'à UN seul reçu : l'adhésion source est relue
    sous verrou, et un second appel lève `RecuDejaEmis`. Ce garde-fou vivait
    dans la vue, où un double clic passait à côté — et où ni l'admin ni le shell
    ne le voyaient.
    """
    if adhesion is not None:
        verrouillee = Adhesion.objects.select_for_update().get(pk=adhesion.pk)
        existant = verrouillee.recus_fiscaux.first()
        if existant is not None:
            raise RecuDejaEmis(
                f"Un reçu fiscal ({existant.numero}) a déjà été émis pour l'adhésion "
                f"de {verrouillee.membre}."
            )

    jour = date_emission or timezone.localdate()

    # get_or_create couvre le 1er reçu de l'année ; on reprend la ligne SOUS
    # VERROU pour incrémenter de façon sûre (unicité garantie sur PostgreSQL).
    CompteurRecu.objects.get_or_create(annee=jour.year)
    compteur = CompteurRecu.objects.select_for_update().get(annee=jour.year)
    compteur.dernier += 1
    compteur.save(update_fields=["dernier"])

    recu = RecuFiscal.objects.create(
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
        # Le donateur est dans les colonnes ci-dessus ; le bénéficiaire et le
        # signataire, eux, vivent ailleurs et peuvent changer après l'émission.
        instantane={
            "version": 1,
            "emetteur": fige.emetteur(ParametresAssociation.load()),
            "signataire": fige.signataire(signataire),
        },
    )
    # Après le commit, pas dedans : un rendu raté n'annule pas un numéro
    # légalement attribué (`robust` journalise au lieu de lever).
    transaction.on_commit(partial(_figer_pdf_recu, recu.pk), robust=True)
    return recu


def donnees_depuis_adhesion(adhesion) -> dict:
    """Valeurs initiales pour pré-remplir le formulaire d'émission depuis une
    adhésion (le bureau complète ensuite l'adresse, absente du modèle Membre)."""
    return {
        "type_versement": RecuFiscal.TypeVersement.COTISATION,
        "montant": adhesion.montant_verse,
        "date_versement": adhesion.date or timezone.localdate(),
        "donateur_nom": str(adhesion.membre),
    }


def _recu_fige(recu: RecuFiscal) -> SimpleNamespace:
    """Le reçu tel qu'il a été émis, sous la forme qu'attend le gabarit Cerfa."""
    return SimpleNamespace(
        numero=recu.numero,
        date_emission=recu.date_emission,
        montant=recu.montant,
        date_versement=recu.date_versement,
        donateur_nom=recu.donateur_nom,
        donateur_adresse=recu.donateur_adresse,
        donateur_code_postal=recu.donateur_code_postal,
        donateur_ville=recu.donateur_ville,
        get_type_versement_display=recu.get_type_versement_display,
        get_forme_display=recu.get_forme_display,
        signataire=fige.en_objet(recu.instantane["signataire"]),
    )


def pdf_de_recu(recu: RecuFiscal, *, apercu: bool = False) -> bytes:
    """Rend le PDF Cerfa d'un reçu.

    Un reçu ÉMIS est rendu depuis son INSTANTANÉ : un Cerfa perdu se reconstruit
    tel qu'il a été délivré, et non au nom que l'association porte aujourd'hui.
    `apercu=True` produit à l'inverse un document filigrané « sans valeur » à
    partir des données vivantes, pour prévisualiser AVANT émission (reçu non
    enregistré, donc sans instantané)."""
    if not apercu and getattr(recu, "instantane", None):
        contexte = {
            "recu": _recu_fige(recu),
            "asso": fige.en_objet(recu.instantane["emetteur"]),
            "apercu": False,
        }
    else:
        contexte = {"recu": recu, "asso": ParametresAssociation.load(), "apercu": apercu}
    return pdf.html_vers_pdf(render_to_string("recu/cerfa.html", contexte))


@transaction.atomic
def assurer_pdf_recu(recu: RecuFiscal) -> None:
    """Garantit que le PDF Cerfa du reçu existe dans le stockage privé.

    Rendu une seule fois — normalement dès l'émission (`_figer_pdf_recu`) ; ce
    rendu à la demande n'est plus qu'un repli, quand le moteur PDF manquait à ce
    moment-là. L'absence de fichier est revérifiée sous verrou : deux premiers
    téléchargements simultanés rendaient sinon deux fois, et le second
    remplaçait la pièce archivée. L'instance reçue récupère le fichier."""
    if recu.fichier:
        return
    courant = RecuFiscal.objects.select_for_update().get(pk=recu.pk)
    if not courant.fichier:
        octets = pdf_de_recu(courant)
        courant.fichier.save(f"recu-{courant.numero}.pdf", ContentFile(octets), save=False)
        courant.save(update_fields=["fichier"])
    recu.refresh_from_db(fields=["fichier"])


def _figer_pdf_recu(recu_pk: int) -> None:
    """Rend et archive le Cerfa d'un reçu qui vient d'être émis.

    Sans moteur PDF (poste Windows sans Pango), la pièce retombe sur le rendu au
    premier téléchargement : moins sûr, mais le numéro reste valable."""
    try:
        assurer_pdf_recu(RecuFiscal.objects.get(pk=recu_pk))
    except pdf.RenduPDFIndisponible as exc:
        logger.warning("PDF du reçu #%s non figé à l'émission : %s", recu_pk, exc)


# --- Bilan budgétaire -------------------------------------------------------

_ZERO = Decimal("0.00")
_CLES_MONTANT = ("recette_prevu", "recette_realise", "depense_prevu", "depense_realise")


def _ligne_vide(nom: str) -> dict:
    ligne = {"categorie": nom}
    for cle in _CLES_MONTANT:
        ligne[cle] = _ZERO
    return ligne


def _completer_soldes(ligne: dict) -> None:
    ligne["solde_prevu"] = ligne["recette_prevu"] - ligne["depense_prevu"]
    ligne["solde_realise"] = ligne["recette_realise"] - ligne["depense_realise"]


def bilan_par_categorie(saison) -> dict:
    """Synthèse budgétaire d'une saison, ventilée par catégorie.

    Pour chaque catégorie : recettes et dépenses, en prévu et en réalisé, avec
    le solde (recettes − dépenses). Renvoie les lignes triées + une ligne de
    totaux. Les transactions sans catégorie sont regroupées sous « Sans
    catégorie »."""
    lignes: dict[str, dict] = {}
    transactions = Transaction.objects.filter(saison=saison).select_related("categorie")
    for t in transactions:
        nom = t.categorie.nom if t.categorie_id else "Sans catégorie"
        ligne = lignes.setdefault(nom, _ligne_vide(nom))
        flux = "recette" if t.type_flux == Transaction.TypeFlux.RECETTE else "depense"
        etat = "prevu" if t.statut == Transaction.Statut.PREVU else "realise"
        ligne[f"{flux}_{etat}"] += t.montant

    totaux = _ligne_vide("Total")
    resultat = []
    for nom in sorted(lignes):
        ligne = lignes[nom]
        _completer_soldes(ligne)
        resultat.append(ligne)
        for cle in _CLES_MONTANT:
            totaux[cle] += ligne[cle]
    _completer_soldes(totaux)

    return {"lignes": resultat, "totaux": totaux}


def tresorerie(saison) -> dict:
    """Trésorerie de référence + prévision, pour la gestion (pas la compta).

    Part du **solde en banque pointé** (singleton `SoldeTresorerie`, saisi par le
    trésorier) et y applique le **reste à réaliser** de la saison selon le budget
    prévisionnel :

        prévisionnelle = solde pointé + (recettes prévues − réalisées)
                                       − (dépenses prévues − réalisées)

    Tout est un repère à rapprocher des comptes réels. Sans saison, on ne projette
    pas (reste à réaliser nul)."""
    solde = SoldeTresorerie.charger()
    if saison is not None:
        totaux = bilan_par_categorie(saison)["totaux"]
        # « Reste à réaliser » = ce qui est budgété mais pas encore réalisé, donc
        # jamais négatif : si le réalisé dépasse déjà le prévu, il ne reste rien.
        reste_a_encaisser = max(_ZERO, totaux["recette_prevu"] - totaux["recette_realise"])
        reste_a_decaisser = max(_ZERO, totaux["depense_prevu"] - totaux["depense_realise"])
    else:
        reste_a_encaisser = _ZERO
        reste_a_decaisser = _ZERO
    return {
        "solde_pointe": solde.montant,
        "date_pointage": solde.date_pointage,
        "note": solde.note,
        "reste_a_encaisser": reste_a_encaisser,
        "reste_a_decaisser": reste_a_decaisser,
        "previsionnelle": solde.montant + reste_a_encaisser - reste_a_decaisser,
    }


def resume_cotisations(saison) -> dict:
    """Chiffres clés cotisations + reçus fiscaux pour le hub Finances.

    Les adhésions sont bornées à la `saison` ; les reçus fiscaux (sans lien
    direct à la saison) sont comptés toutes périodes confondues."""
    adhesions = Adhesion.objects.filter(saison=saison) if saison else Adhesion.objects.none()
    montants = adhesions.aggregate(verse=Sum("montant_verse"), attendu=Sum("montant_attendu"))
    recus = RecuFiscal.objects.aggregate(nb=Count("id"), montant=Sum("montant"))
    return {
        "adhesions_nb": adhesions.count(),
        "adhesions_en_attente": adhesions.filter(statut=Adhesion.Statut.EN_ATTENTE).count(),
        "verse": montants["verse"] or _ZERO,
        "attendu": montants["attendu"] or _ZERO,
        "recus_nb": recus["nb"] or 0,
        "recus_montant": recus["montant"] or _ZERO,
    }


_ENTETES_BILAN = [
    "Catégorie",
    "Recettes prévues",
    "Recettes réalisées",
    "Dépenses prévues",
    "Dépenses réalisées",
    "Solde prévu",
    "Solde réalisé",
]


def classeur_bilan(saison) -> bytes:
    """Exporte le bilan par catégorie d'une saison au format Excel (.xlsx)."""
    from io import BytesIO

    from openpyxl import Workbook  # import paresseux (dépendance optionnelle)

    bilan = bilan_par_categorie(saison)
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Bilan"
    feuille.append(_ENTETES_BILAN)

    cles = _CLES_MONTANT + ("solde_prevu", "solde_realise")
    for ligne in [*bilan["lignes"], bilan["totaux"]]:
        feuille.append([ligne["categorie"], *[float(ligne[cle]) for cle in cles]])

    flux = BytesIO()
    classeur.save(flux)
    return flux.getvalue()
