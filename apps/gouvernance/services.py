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

from django.db.models import Count

from apps.budget.models import Adhesion

from .models import ParametresGouvernance, Presence, Resolution, Reunion

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
