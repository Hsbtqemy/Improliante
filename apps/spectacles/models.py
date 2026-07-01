"""Modèles du domaine « Spectacles / Projets » (cf. cahier §6).

Distinction clé : le `Spectacle` est l'œuvre (titre, synopsis, équipe, affiche)
et existe **indépendamment des dates**. Ses représentations datées sont des
`Evenement` de l'agenda (0..n), reliés au spectacle — un spectacle peut exister
sans aucune représentation (« nos créations en cours »).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import Horodatage, Moderation


class Spectacle(Horodatage, Moderation):
    """Œuvre / projet porté par l'association, un membre ou un collectif."""

    class TypePortage(models.TextChoices):
        ASSOCIATION = "association", "Production de l'association"
        PERSONNEL = "personnel", "Projet personnel d'un membre"
        COLLECTIF = "collectif", "Projet collectif"

    class StatutProjet(models.TextChoices):
        EN_CREATION = "en_creation", "En création"
        EN_REPETITION = "en_repetition", "En répétition"
        A_L_AFFICHE = "a_l_affiche", "À l'affiche"
        ARCHIVE = "archive", "Archivé"

    titre = models.CharField(max_length=200)
    synopsis = models.TextField(blank=True)
    note_intention = models.TextField("note d'intention", blank=True)

    type_portage = models.CharField(
        "type de portage",
        max_length=12,
        choices=TypePortage.choices,
        default=TypePortage.ASSOCIATION,
    )
    porteurs = models.ManyToManyField(
        "coeur.Membre",
        blank=True,
        related_name="spectacles_portes",
        verbose_name="porteurs",
        help_text="Surtout pour les projets personnels ou collectifs.",
    )
    statut_projet = models.CharField(
        max_length=14,
        choices=StatutProjet.choices,
        default=StatutProjet.EN_CREATION,
    )

    metteur_en_scene = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mises_en_scene",
        verbose_name="metteur·euse en scène (membre)",
    )
    metteur_en_scene_externe = models.CharField(
        "metteur·euse en scène (externe)",
        max_length=200,
        blank=True,
        help_text="Si la mise en scène n'est pas assurée par un membre.",
    )

    affiche = models.ForeignKey(
        "medias.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="affiche",
    )

    duree_minutes = models.PositiveIntegerField("durée (minutes)", null=True, blank=True)
    genre = models.CharField(max_length=120, blank=True)
    public_vise = models.CharField("public visé", max_length=120, blank=True)

    class Meta:
        verbose_name = "spectacle / projet"
        verbose_name_plural = "spectacles / projets"
        ordering = ["titre"]

    def __str__(self) -> str:
        return self.titre


class LigneDistribution(models.Model):
    """Une ligne de distribution : soit un `Membre`, soit un nom externe libre.

    Compromis assumé (cahier §6) : pas de socle Personne. Un intervenant
    extérieur récurrent est ressaisi à chaque fois.
    """

    spectacle = models.ForeignKey(
        Spectacle,
        on_delete=models.CASCADE,
        related_name="distribution",
    )
    membre = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="roles_distribution",
        verbose_name="membre",
    )
    nom_externe = models.CharField(
        "intervenant·e extérieur·e",
        max_length=200,
        blank=True,
    )
    role = models.CharField(
        "rôle",
        max_length=200,
        help_text="Ex. comédien·ne, mise en scène, technique, musique…",
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "ligne de distribution"
        verbose_name_plural = "distribution"
        ordering = ["ordre", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(membre__isnull=False, nom_externe="")
                    | models.Q(membre__isnull=True) & ~models.Q(nom_externe="")
                ),
                name="distribution_membre_ou_nom_externe",
                violation_error_message=(
                    "Renseignez soit un membre, soit un nom externe (exactement l'un des deux)."
                ),
            )
        ]

    def clean(self) -> None:
        """Exactement l'un de `membre` / `nom_externe` doit être renseigné."""
        a_membre = self.membre_id is not None
        a_nom = bool(self.nom_externe.strip())
        if a_membre == a_nom:
            raise ValidationError(
                "Renseignez soit un membre, soit un nom externe (exactement l'un des deux)."
            )

    def __str__(self) -> str:
        qui = self.membre if self.membre_id else self.nom_externe
        return f"{qui} — {self.role}"


class ImageSpectacle(models.Model):
    """Image de la galerie d'un spectacle, avec ordre d'affichage (drag & drop)."""

    spectacle = models.ForeignKey(
        Spectacle,
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
                fields=["spectacle", "media"],
                name="image_spectacle_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.spectacle} — image {self.ordre}"
