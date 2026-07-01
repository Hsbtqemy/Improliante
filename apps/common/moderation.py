"""Services de transition du cycle de modération partagé.

Le cycle `brouillon → proposé → publié / refusé` (mixin `Moderation`) est le
même pour l'agenda, les spectacles et la gouvernance. Les transitions déclen-
chées par l'auteur d'une fiche (un membre depuis son espace) sont centralisées
ici plutôt que dupliquées dans chaque vue — CLAUDE.md règle 7 (« même logique
réutilisée partout ») et « pas de logique métier dans les routes ».
"""

from __future__ import annotations

from django.utils import timezone

from apps.common.models import Moderation

# États dans lesquels l'auteur d'une fiche peut encore la modifier ou la
# (re)soumettre. Une fiche « proposée » attend l'avis du bureau (verrouillée
# côté auteur) ; une fiche « publiée » est en ligne (toute retouche repasserait
# par la modération, hors périmètre de cette tranche).
ETATS_EDITABLES_PAR_AUTEUR = frozenset(
    {
        Moderation.StatutModeration.BROUILLON,
        Moderation.StatutModeration.REFUSE,
    }
)


class TransitionModerationInvalide(Exception):
    """Transition demandée depuis un état qui ne l'autorise pas."""


def peut_etre_edite_par_auteur(fiche: Moderation) -> bool:
    """Vrai si l'auteur peut encore éditer / soumettre cette fiche."""
    return fiche.statut_moderation in ETATS_EDITABLES_PAR_AUTEUR


def soumettre_a_moderation(fiche: Moderation) -> None:
    """Passe une fiche `brouillon`/`refusé` à `proposé`.

    Efface le motif de refus précédent (nouvelle soumission = repartir propre).
    Lève `TransitionModerationInvalide` si la fiche n'est pas dans un état
    soumissible (déjà proposée, ou publiée).
    """
    if not peut_etre_edite_par_auteur(fiche):
        raise TransitionModerationInvalide(
            f"Une fiche au statut « {fiche.get_statut_moderation_display()} » "
            "ne peut pas être soumise à la modération."
        )
    fiche.statut_moderation = Moderation.StatutModeration.PROPOSE
    fiche.motif_refus = ""
    fiche.save()


def valider(fiche: Moderation, *, par) -> None:
    """Publie une fiche `proposée` (action du bureau).

    Enregistre le valideur et la date de publication. Lève
    `TransitionModerationInvalide` si la fiche n'est pas au statut « proposé ».
    """
    if fiche.statut_moderation != Moderation.StatutModeration.PROPOSE:
        raise TransitionModerationInvalide("Seule une fiche « proposée » peut être publiée.")
    fiche.statut_moderation = Moderation.StatutModeration.PUBLIE
    fiche.valide_par = par
    fiche.date_publication = timezone.now()
    fiche.motif_refus = ""
    fiche.save()


def refuser(fiche: Moderation, *, par, motif: str) -> None:
    """Refuse une fiche `proposée` avec un motif (action du bureau).

    Le motif est obligatoire : c'est lui que l'auteur verra pour corriger.
    Lève `TransitionModerationInvalide` si la fiche n'est pas « proposée »,
    `ValueError` si le motif est vide.
    """
    if fiche.statut_moderation != Moderation.StatutModeration.PROPOSE:
        raise TransitionModerationInvalide("Seule une fiche « proposée » peut être refusée.")
    if not motif.strip():
        raise ValueError("Un motif de refus est obligatoire.")
    fiche.statut_moderation = Moderation.StatutModeration.REFUSE
    fiche.valide_par = par
    fiche.motif_refus = motif.strip()
    fiche.save()
