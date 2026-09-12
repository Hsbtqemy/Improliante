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
from django.utils import timezone

from apps.budget.models import Adhesion
from apps.coeur.models import Membre, ParametresAssociation
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


@dataclass(frozen=True)
class ReglesApplicables:
    """Les seuils statutaires qui valent pour une réunion donnée."""

    quorum: Decimal
    majorite_simple: Decimal
    majorite_qualifiee: Decimal
    base_majorite: str
    figees: bool


def _seuil_quorum(reunion: Reunion, params: ParametresGouvernance) -> Decimal:
    if reunion.type_reunion == Reunion.TypeReunion.AG_EXTRAORDINAIRE:
        return params.quorum_ag_extraordinaire
    if reunion.type_reunion == Reunion.TypeReunion.AG_ORDINAIRE:
        return params.quorum_ag_ordinaire
    return Decimal("0")  # réunion de bureau : pas de quorum statutaire


def regles_applicables(reunion: Reunion) -> ReglesApplicables:
    """Les règles de cette réunion : figées si elle est close, courantes sinon.

    Une réunion tenue s'est tenue sous les statuts de son jour. Les relire dans
    les paramètres courants faisait tomber une AG de janvier quand on relevait le
    quorum en février — et changeait l'adoption d'une résolution sans que
    personne n'ait touché à un vote."""
    figees = reunion.regles_figees
    if figees:
        return ReglesApplicables(
            quorum=Decimal(figees["quorum"]),
            majorite_simple=Decimal(figees["majorite_simple"]),
            majorite_qualifiee=Decimal(figees["majorite_qualifiee"]),
            base_majorite=figees["base_majorite"],
            figees=True,
        )
    params = ParametresGouvernance.load()
    return ReglesApplicables(
        quorum=_seuil_quorum(reunion, params),
        majorite_simple=params.majorite_simple,
        majorite_qualifiee=params.majorite_qualifiee,
        base_majorite=params.base_majorite,
        figees=False,
    )


def figer_les_regles(reunion: Reunion) -> bool:
    """Fige les règles statutaires d'une réunion CLOSE (archivée).

    Idempotent, et c'est le cœur du geste : refiger remplacerait les règles du
    jour par celles d'aujourd'hui, précisément ce qu'on cherche à empêcher.
    Retourne True si le gel vient d'avoir lieu."""
    if reunion.regles_figees or reunion.statut != Reunion.Statut.ARCHIVEE:
        return False
    regles = regles_applicables(reunion)
    reunion.regles_figees = {
        "version": 1,
        "quorum": str(regles.quorum),
        "majorite_simple": str(regles.majorite_simple),
        "majorite_qualifiee": str(regles.majorite_qualifiee),
        "base_majorite": regles.base_majorite,
        "fige_le": timezone.now().isoformat(),
    }
    reunion.save(update_fields=["regles_figees"])
    return True


def calcul_quorum(reunion: Reunion) -> ResultatQuorum:
    """Calcule le quorum sur le REGISTRE ÉLECTORAL de la réunion.

    Dénominateur : les électeurs inscrits au registre (cf.
    `preremplir_droit_de_vote`), absents compris. Seuil : celui figé à la
    clôture si la réunion est close, celui des paramètres courants sinon."""
    votants = reunion.presences.filter(peut_voter=True)
    electorat = votants.count()
    presents_representes = votants.filter(
        statut__in=[Presence.Statut.PRESENT, Presence.Statut.REPRESENTE]
    ).count()

    if reunion.type_reunion not in (
        Reunion.TypeReunion.AG_ORDINAIRE,
        Reunion.TypeReunion.AG_EXTRAORDINAIRE,
    ):  # réunion de bureau : pas de quorum statutaire
        return ResultatQuorum(False, True, presents_representes, electorat, Decimal("0"))

    seuil = regles_applicables(reunion).quorum
    atteint = electorat > 0 and _proportion(presents_representes, electorat) >= seuil
    return ResultatQuorum(True, atteint, presents_representes, electorat, seuil)


@dataclass(frozen=True)
class ResultatResolution:
    adoptee: bool
    pour: int
    contre: int
    abstention: int
    base: int


def resultat_resolution(resolution: Resolution, *, regles=None) -> ResultatResolution:
    """Détermine si une résolution est adoptée selon son type de majorité.

    Les seuils sont ceux applicables à SA réunion : figés si elle est close.
    Une boucle sur les résolutions d'une même réunion passe `regles` une fois
    pour toutes — sinon chaque résolution va rechercher sa réunion et ses
    paramètres, une requête par ligne."""
    params = regles or regles_applicables(resolution.reunion)
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


def donner_pouvoir(
    reunion: Reunion, mandant, mandataire, *, par_le_bureau: bool = False
) -> Pouvoir:
    """Le mandant donne pouvoir au mandataire pour cette réunion.

    Marque le mandant « représenté » et crée/actualise son pouvoir. Vérifie :
    mandataire différent du mandant, plafond `max_pouvoirs_par_personne`, et —
    pour un membre — réunion encore ouverte aux réponses.

    `par_le_bureau=True` lève cette dernière condition, et elle seule : un
    pouvoir papier se saisit pendant ou après la séance. Le plafond, lui, est
    STATUTAIRE et ne dépend pas de qui saisit — le bureau écrivait jusqu'ici
    directement en base, sans aucun contrôle.

    Le décompte se fait sous verrou de la réunion : deux pouvoirs donnés au même
    instant au même mandataire lisaient sinon le même total, et passaient tous
    les deux."""
    if mandataire == mandant:
        raise ReponseConvocationImpossible("Vous ne pouvez pas vous donner pouvoir à vous-même.")
    with transaction.atomic():
        reunion = Reunion.objects.select_for_update().get(pk=reunion.pk)
        if not par_le_bureau and not _accepte_les_reponses(reunion):
            raise ReponseConvocationImpossible("Cette convocation n'accepte plus de réponse.")
        params = ParametresGouvernance.load()
        deja_detenus = (
            reunion.pouvoirs.filter(mandataire=mandataire).exclude(mandant=mandant).count()
        )
        if deja_detenus >= params.max_pouvoirs_par_personne:
            raise ReponseConvocationImpossible(
                f"{mandataire} détient déjà le maximum de pouvoirs "
                f"({params.max_pouvoirs_par_personne})."
            )
        Presence.objects.update_or_create(
            reunion=reunion, membre=mandant, defaults={"statut": Presence.Statut.REPRESENTE}
        )
        pouvoir, _ = Pouvoir.objects.update_or_create(
            reunion=reunion, mandant=mandant, defaults={"mandataire": mandataire}
        )
    return pouvoir


def preremplir_droit_de_vote(reunion: Reunion, saison=None) -> int:
    """Ouvre le REGISTRE ÉLECTORAL de la réunion et fige les droits de vote.

    Tout électeur y entre, qu'il vienne ou non : le quorum se calcule sur
    l'électorat, et un registre réduit aux personnes qu'on a pensé à inscrire le
    ferait paraître atteint alors qu'il ne l'est pas — vingt électeurs, cinq
    inscrits, quorum à 100 %. Les électeurs ajoutés d'office le sont comme
    ABSENTS ; le bureau corrige ensuite ce qu'il constate en séance.

    Est électeur tout membre actif si `vote_reserve_aux_membres_a_jour` est faux ;
    sinon, tout membre actif à jour de cotisation pour la `saison` donnée. Une
    présence déjà enregistrée garde son statut : seul son droit de vote est
    recalculé, et il est ainsi figé au moment de la tenue (§8.4).

    Retourne le nombre de présences créées ou modifiées.
    """
    params = ParametresGouvernance.load()
    reserve = params.vote_reserve_aux_membres_a_jour
    if reserve and saison is None:
        raise ValueError("Une saison est requise quand le vote est réservé aux membres à jour.")

    electeurs = set(Membre.objects.filter(actif=True).values_list("id", flat=True))
    if reserve:
        electeurs &= set(
            Adhesion.objects.filter(
                saison=saison,
                statut__in=[Adhesion.Statut.PAYEE, Adhesion.Statut.EXONEREE],
            ).values_list("membre_id", flat=True)
        )

    touchees = 0
    with transaction.atomic():
        # Sous verrou : deux préremplissages lancés ensemble calculeraient les
        # mêmes manquants et se heurteraient à l'unicité (réunion, membre).
        reunion = Reunion.objects.select_for_update().get(pk=reunion.pk)
        if reunion.statut == Reunion.Statut.ARCHIVEE:
            raise ValueError(
                "Cette réunion est close : son registre électoral ne se rouvre pas. "
                "Les électeurs inscrits ce jour-là font son quorum."
            )
        deja_inscrits = {presence.membre_id: presence for presence in reunion.presences.all()}
        for presence in deja_inscrits.values():
            electeur = presence.membre_id in electeurs
            if presence.peut_voter != electeur:
                presence.peut_voter = electeur
                presence.save(update_fields=["peut_voter"])
                touchees += 1
        # Le registre ne s'ouvre que pour une AG : le quorum ne s'applique qu'à
        # elle, et inscrire d'office toute l'association à une réunion de bureau
        # produirait une liste de présences qui ne veut rien dire.
        if reunion.type_reunion not in (
            Reunion.TypeReunion.AG_ORDINAIRE,
            Reunion.TypeReunion.AG_EXTRAORDINAIRE,
        ):
            return touchees
        manquants = electeurs - set(deja_inscrits)
        Presence.objects.bulk_create(
            [
                Presence(
                    reunion=reunion,
                    membre_id=membre_id,
                    statut=Presence.Statut.ABSENT,
                    peut_voter=True,
                )
                for membre_id in manquants
            ]
        )
        touchees += len(manquants)
    return touchees


def generer_compte_rendu(reunion: Reunion, *, par) -> Document:
    """Génère le PV (PDF) d'une réunion et le range dans la GED.

    Le PV assemble les **notes de séance** (synthèse + notes par point d'ordre du
    jour) avec les **données déjà saisies** (présences, pouvoirs, quorum,
    résolutions et leurs résultats) — aucune ressaisie. Le PDF est déposé comme
    Document de confidentialité « Membres » et rattaché à `reunion.compte_rendu`.

    « Membres », quel que soit le type de réunion : un compte rendu rend compte à
    TOUS les membres, celui d'une réunion de bureau compris — décision de
    l'association (sept. 2026). La page d'une réunion de bureau reste réservée
    au bureau ; son PV, non. Ce n'est pas une fuite, et un test le fixe
    (`espace_membre/tests.py`).

    Régénérer **remplace** le fichier du compte-rendu existant (pas de doublon)."""
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

    # Une seule lecture des règles pour toute la réunion : dans la compréhension
    # ci-dessous, l'appel serait refait à chaque résolution.
    regles = regles_applicables(reunion)
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
        "resolutions": [
            (r, resultat_resolution(r, regles=regles)) for r in reunion.resolutions.all()
        ],
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
