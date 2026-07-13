"""Services métier du domaine « Gouvernance » (zone à risque, cf. cahier §8).

Calculs statutaires (quorum, adoption des résolutions, contrôle des pouvoirs) en
lisant `ParametresGouvernance` — aucune règle n'est codée en dur.

Conventions (documentées, ajustables via les paramètres) :
- Quorum = (présents + représentés parmi les votants) / électorat enregistré,
  l'électorat étant le nombre de `Presence` avec `peut_voter=True` de la réunion.
  Seuil selon le type d'AG ; pas de quorum pour une réunion de bureau.
- Adoption : dénominateur = suffrages exprimés (défaut) ou présents/représentés,
  selon `base_majorite`. Majorité simple = « > seuil » ; qualifiée = « ≥ seuil » ;
  unanimité = aucun vote contre (et au moins un pour).
- Les proportions sont comparées à 3 décimales (comme les seuils stockés), pour
  que « 2/3 » satisfasse bien un seuil de 0.667.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count
from django.template.loader import render_to_string

from apps.budget.models import Adhesion
from apps.coeur.models import ParametresAssociation
from apps.common import pdf
from apps.documents.models import Document
from apps.documents.services import televerser_fichier

from .models import ParametresGouvernance, Pouvoir, Presence, Resolution, Reunion

_TROIS_DECIMALES = Decimal("0.001")


def _proportion(numerateur: int, denominateur: int) -> Decimal:
    """Proportion arrondie à 3 décimales (cohérent avec les seuils stockés)."""
    return (Decimal(numerateur) / Decimal(denominateur)).quantize(_TROIS_DECIMALES)


@dataclass(frozen=True)
class ResultatQuorum:
    applicable: bool
    atteint: bool
    presents_representes: int
    electorat: int
    seuil: Decimal


def calcul_quorum(reunion: Reunion) -> ResultatQuorum:
    """Calcule le quorum d'une réunion à partir des présences enregistrées."""
    params = ParametresGouvernance.load()
    votants = reunion.presences.filter(peut_voter=True)
    electorat = votants.count()
    presents_representes = votants.filter(
        statut__in=[Presence.Statut.PRESENT, Presence.Statut.REPRESENTE]
    ).count()

    if reunion.type_reunion == Reunion.TypeReunion.AG_EXTRAORDINAIRE:
        seuil = params.quorum_ag_extraordinaire
    elif reunion.type_reunion == Reunion.TypeReunion.AG_ORDINAIRE:
        seuil = params.quorum_ag_ordinaire
    else:  # réunion de bureau : pas de quorum statutaire
        return ResultatQuorum(False, True, presents_representes, electorat, Decimal("0"))

    atteint = electorat > 0 and _proportion(presents_representes, electorat) >= seuil
    return ResultatQuorum(True, atteint, presents_representes, electorat, seuil)


@dataclass(frozen=True)
class ResultatResolution:
    adoptee: bool
    pour: int
    contre: int
    abstention: int
    base: int


def resultat_resolution(resolution: Resolution) -> ResultatResolution:
    """Détermine si une résolution est adoptée selon son type de majorité."""
    params = ParametresGouvernance.load()
    pour = resolution.nombre_pour
    contre = resolution.nombre_contre
    abstention = resolution.nombre_abstention

    if params.base_majorite == ParametresGouvernance.BaseMajorite.PRESENTS:
        base = pour + contre + abstention
    else:
        base = pour + contre

    type_majorite = resolution.type_majorite
    if type_majorite == Resolution.TypeMajorite.UNANIMITE:
        adoptee = contre == 0 and pour > 0
    elif base == 0:
        adoptee = False
    elif type_majorite == Resolution.TypeMajorite.QUALIFIEE:
        adoptee = _proportion(pour, base) >= params.majorite_qualifiee
    else:  # majorité simple
        adoptee = _proportion(pour, base) > params.majorite_simple

    return ResultatResolution(adoptee, pour, contre, abstention, base)


def mandataires_en_exces(reunion: Reunion) -> dict[int, int]:
    """Mandataires détenant plus de pouvoirs que le maximum autorisé.

    Retourne ``{membre_id: nombre_de_pouvoirs}`` ; dict vide si tout est conforme.
    """
    params = ParametresGouvernance.load()
    exces = (
        reunion.pouvoirs.values("mandataire")
        .annotate(n=Count("id"))
        .filter(n__gt=params.max_pouvoirs_par_personne)
    )
    return {row["mandataire"]: row["n"] for row in exces}


class ReponseConvocationImpossible(Exception):
    """Réponse d'un membre à une convocation refusée : réunion close aux réponses,
    mandataire invalide, ou plafond de pouvoirs atteint."""


def _accepte_les_reponses(reunion: Reunion) -> bool:
    """Un membre ne peut répondre que tant que l'AG est « Convoquée »."""
    return reunion.statut == Reunion.Statut.CONVOQUEE


def enregistrer_presence_membre(reunion: Reunion, membre, statut) -> Presence:
    """Le membre déclare lui-même sa présence (présent / absent).

    Retire un éventuel pouvoir qu'il avait donné (il n'est plus représenté). Ne
    touche PAS `peut_voter` : le droit de vote est fixé par le bureau selon
    l'adhésion à jour, figé à la tenue de l'AG (§8.4)."""
    if not _accepte_les_reponses(reunion):
        raise ReponseConvocationImpossible("Cette convocation n'accepte plus de réponse.")
    with transaction.atomic():
        presence, _ = Presence.objects.update_or_create(
            reunion=reunion, membre=membre, defaults={"statut": statut}
        )
        Pouvoir.objects.filter(reunion=reunion, mandant=membre).delete()
    return presence


def donner_pouvoir(reunion: Reunion, mandant, mandataire) -> Pouvoir:
    """Le mandant donne pouvoir au mandataire pour cette réunion.

    Marque le mandant « représenté » et crée/actualise son pouvoir. Vérifie :
    mandataire différent du mandant, plafond `max_pouvoirs_par_personne`, et
    réunion encore ouverte aux réponses."""
    if not _accepte_les_reponses(reunion):
        raise ReponseConvocationImpossible("Cette convocation n'accepte plus de réponse.")
    if mandataire == mandant:
        raise ReponseConvocationImpossible("Vous ne pouvez pas vous donner pouvoir à vous-même.")
    params = ParametresGouvernance.load()
    deja_detenus = reunion.pouvoirs.filter(mandataire=mandataire).exclude(mandant=mandant).count()
    if deja_detenus >= params.max_pouvoirs_par_personne:
        raise ReponseConvocationImpossible(
            f"{mandataire} détient déjà le maximum de pouvoirs "
            f"({params.max_pouvoirs_par_personne})."
        )
    with transaction.atomic():
        Presence.objects.update_or_create(
            reunion=reunion, membre=mandant, defaults={"statut": Presence.Statut.REPRESENTE}
        )
        pouvoir, _ = Pouvoir.objects.update_or_create(
            reunion=reunion, mandant=mandant, defaults={"mandataire": mandataire}
        )
    return pouvoir


def preremplir_droit_de_vote(reunion: Reunion, saison=None) -> int:
    """Renseigne `Presence.peut_voter` pour la réunion, selon l'adhésion à jour.

    Si `vote_reserve_aux_membres_a_jour` est faux, tout le monde peut voter.
    Sinon, seul un membre à jour de cotisation pour la `saison` donnée le peut
    (le droit de vote est ainsi figé au moment de la tenue). Retourne le nombre
    de présences effectivement modifiées.
    """
    params = ParametresGouvernance.load()
    reserve = params.vote_reserve_aux_membres_a_jour
    if reserve and saison is None:
        raise ValueError("Une saison est requise quand le vote est réservé aux membres à jour.")

    membres_a_jour: set[int] = set()
    if reserve:
        membres_a_jour = set(
            Adhesion.objects.filter(
                saison=saison,
                statut__in=[Adhesion.Statut.PAYEE, Adhesion.Statut.EXONEREE],
            ).values_list("membre_id", flat=True)
        )

    modifies = 0
    for presence in reunion.presences.all():
        nouveau = (not reserve) or (presence.membre_id in membres_a_jour)
        if presence.peut_voter != nouveau:
            presence.peut_voter = nouveau
            presence.save(update_fields=["peut_voter"])
            modifies += 1
    return modifies


def generer_compte_rendu(reunion: Reunion, *, par) -> Document:
    """Génère le PV (PDF) d'une réunion et le range dans la GED.

    Le PV assemble les **notes de séance** (synthèse + notes par point d'ordre du
    jour) avec les **données déjà saisies** (présences, pouvoirs, quorum,
    résolutions et leurs résultats) — aucune ressaisie. Le PDF est déposé comme
    Document (confidentialité « Membres », donc visible des convoqués) et rattaché
    à `reunion.compte_rendu`. Régénérer **remplace** le fichier du compte-rendu
    existant (pas de doublon)."""
    presences = reunion.presences.select_related("membre").order_by("membre__nom", "membre__prenom")

    # Déroulé : préambule (blocs sans point) + chaque point suivi de ses blocs.
    sujets = list(reunion.sujets.order_by("ordre_du_jour", "id"))
    blocs_intro = []
    blocs_par_sujet: dict[int, list] = {}
    for bloc in reunion.blocs.all():
        if bloc.apres_sujet_id:
            blocs_par_sujet.setdefault(bloc.apres_sujet_id, []).append(bloc)
        else:
            blocs_intro.append(bloc)
    for sujet in sujets:
        sujet.blocs_suivants = blocs_par_sujet.get(sujet.pk, [])

    contexte = {
        "reunion": reunion,
        "asso": ParametresAssociation.load(),
        "quorum": calcul_quorum(reunion),
        "ordre_du_jour": sujets,
        "blocs_intro": blocs_intro,
        "pouvoirs": reunion.pouvoirs.select_related("mandant", "mandataire"),
        "presents": presences.filter(statut=Presence.Statut.PRESENT),
        "representes": presences.filter(statut=Presence.Statut.REPRESENTE),
        "excuses": presences.filter(statut=Presence.Statut.EXCUSE),
        "absents": presences.filter(statut=Presence.Statut.ABSENT),
        "resolutions": [(r, resultat_resolution(r)) for r in reunion.resolutions.all()],
    }
    octets = pdf.html_vers_pdf(render_to_string("pv/pv.html", contexte))
    nom = f"pv-reunion-{reunion.pk}.pdf"

    if reunion.compte_rendu_id:
        doc = reunion.compte_rendu
        doc.fichier.delete(save=False)
        doc.fichier.save(nom, ContentFile(octets), save=True)
    else:
        doc = televerser_fichier(
            None,
            titre=f"Compte-rendu — {reunion.titre}",
            fichier=ContentFile(octets, name=nom),
            par=par,
            confidentialite=Document.Confidentialite.MEMBRES,
        )
        reunion.compte_rendu = doc
        reunion.save(update_fields=["compte_rendu"])
    return doc
