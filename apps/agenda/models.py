"""Modèles du domaine « Agenda » (cf. cahier §7).

Un `Evenement` est une occurrence datée. Relié à un `Spectacle`, il en constitue
une **représentation** (et hérite à l'affichage de sa description, ses photos, sa
distribution). Visibilité à trois niveaux (public / membres / interne) ; cycle de
modération partagé : le membre propose, le bureau valide et fixe la visibilité.
En v1, un événement = une date (pas de récurrence).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import Horodatage, Moderation


class Evenement(Horodatage, Moderation):
    """Occurrence datée, éventuellement représentation d'un spectacle."""

    class Visibilite(models.TextChoices):
        PUBLIC = "public", "Public"
        MEMBRES = "membres", "Membres"
        INTERNE = "interne", "Interne"

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    date_debut = models.DateTimeField("début")
    date_fin = models.DateTimeField("fin", null=True, blank=True)

    lieu = models.ForeignKey(
        "coeur.Lieu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evenements",
        verbose_name="lieu (fiche)",
    )
    lieu_texte = models.CharField("lieu (texte libre)", max_length=255, blank=True)

    visibilite = models.CharField(
        "visibilité",
        max_length=8,
        choices=Visibilite.choices,
        default=Visibilite.PUBLIC,
    )

    spectacle = models.ForeignKey(
        "spectacles.Spectacle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="representations",
        verbose_name="représentation de",
    )

    affiche = models.ForeignKey(
        "medias.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="affiche",
    )

    intervenants = models.ManyToManyField(
        "coeur.Membre",
        through="Intervention",
        related_name="evenements",
        blank=True,
        verbose_name="intervenants",
    )

    class Meta:
        verbose_name = "événement"
        verbose_name_plural = "événements"
        ordering = ["-date_debut"]

    def __str__(self) -> str:
        return self.titre

    def clean(self) -> None:
        """La fin, si renseignée, ne peut pas précéder le début."""
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin ne peut pas précéder le début."})


class Intervention(models.Model):
    """Participation d'un membre à un événement, avec son rôle."""

    evenement = models.ForeignKey(
        Evenement,
        on_delete=models.CASCADE,
        related_name="interventions",
    )
    membre = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.PROTECT,
        related_name="interventions",
    )
    role = models.CharField(
        "rôle",
        max_length=120,
        blank=True,
        help_text="Ex. organisateur·rice, participant·e…",
    )

    class Meta:
        verbose_name = "intervenant·e"
        verbose_name_plural = "intervenants"
        constraints = [
            models.UniqueConstraint(
                fields=["evenement", "membre"],
                name="intervention_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.membre} — {self.role}" if self.role else str(self.membre)


class ImageEvenement(models.Model):
    """Image de la galerie d'un événement, avec ordre d'affichage."""

    evenement = models.ForeignKey(
        Evenement,
        on_delete=models.CASCADE,
        related_name="images",
    )
    media = models.ForeignKey(
        "medias.Media",
        on_delete=models.CASCADE,
        related_name="+",
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "image de la galerie"
        verbose_name_plural = "galerie"
        ordering = ["ordre", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["evenement", "media"],
                name="image_evenement_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.evenement} — image {self.ordre}"
