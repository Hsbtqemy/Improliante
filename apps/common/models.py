"""Modèles abstraits partagés entre domaines (aucune table propre).

- `Horodatage` : dates de création / modification automatiques.
- `Moderation` : cycle de modération `brouillon → proposé → publié / refusé`
  avec traçabilité `cree_par` / `valide_par` et date de publication.

Le cycle de modération est le même pour l'agenda, les spectacles et la
gouvernance (cf. CLAUDE.md règle 7 : « même logique réutilisée partout »).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Horodatage(models.Model):
    """Ajoute les dates de création et de dernière modification."""

    date_creation = models.DateTimeField("créé le", auto_now_add=True)
    date_modification = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


class Moderation(models.Model):
    """Cycle de modération partagé + traçabilité auteur / valideur.

    Les related_name utilisent `%(app_label)s_%(class)s_...` pour rester
    uniques quel que soit le modèle concret qui hérite de ce mixin.
    """

    class StatutModeration(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PROPOSE = "propose", "Proposé"
        PUBLIE = "publie", "Publié"
        REFUSE = "refuse", "Refusé"

    statut_moderation = models.CharField(
        "statut de modération",
        max_length=12,
        choices=StatutModeration.choices,
        default=StatutModeration.BROUILLON,
    )
    motif_refus = models.TextField("motif de refus", blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_crees",
        verbose_name="créé par",
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_valides",
        verbose_name="validé par",
    )
    date_publication = models.DateTimeField("date de publication", null=True, blank=True)
    modifie_apres_publication = models.BooleanField(
        "modifié depuis la publication",
        default=False,
        help_text=(
            "L'auteur a retouché la fiche après sa mise en ligne : à revoir par le "
            "bureau (contrôle a posteriori). Les changements sont déjà publiés."
        ),
    )

    class Meta:
        abstract = True

    @property
    def est_publie(self) -> bool:
        """Vrai si la fiche est au statut « publié »."""
        return self.statut_moderation == self.StatutModeration.PUBLIE
