"""Modèles du domaine « Médias ».

`Media` centralise les images (affiches, galeries, portraits de membres) et les
vidéos référencées par lien externe (YouTube/Vimeo — pas d'hébergement lourd).
Le texte alternatif (`alt`) est OBLIGATOIRE : accessibilité (cf. cahier §11),
« pas de média sans alt ».
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Media(models.Model):
    """Image téléversée ou vidéo externe, réutilisable par les autres domaines."""

    class TypeMedia(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Vidéo (lien externe)"

    type_media = models.CharField(
        "type",
        max_length=10,
        choices=TypeMedia.choices,
        default=TypeMedia.IMAGE,
    )
    fichier = models.ImageField(
        "fichier image",
        upload_to="medias/%Y/%m/",
        blank=True,
        help_text="Pour un média de type image.",
    )
    url_externe = models.URLField(
        "lien vidéo",
        blank=True,
        help_text="Pour une vidéo : URL YouTube ou Vimeo.",
    )
    alt = models.CharField(
        "texte alternatif",
        max_length=255,
        help_text="Obligatoire (accessibilité) : décrit le média pour les lecteurs d'écran.",
    )
    legende = models.CharField("légende", max_length=255, blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medias_ajoutes",
        verbose_name="ajouté par",
    )
    date_creation = models.DateTimeField("ajouté le", auto_now_add=True)

    class Meta:
        verbose_name = "média"
        verbose_name_plural = "médias"
        ordering = ["-date_creation"]

    def __str__(self) -> str:
        return self.alt or self.legende or f"Média #{self.pk}"

    def clean(self) -> None:
        """Cohérence : une image porte un fichier, une vidéo un lien externe."""
        erreurs: dict[str, str] = {}
        if self.type_media == self.TypeMedia.IMAGE and not self.fichier:
            erreurs["fichier"] = "Une image doit comporter un fichier."
        if self.type_media == self.TypeMedia.VIDEO and not self.url_externe:
            erreurs["url_externe"] = "Une vidéo doit comporter un lien externe (YouTube/Vimeo)."
        if erreurs:
            raise ValidationError(erreurs)
