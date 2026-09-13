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

from apps.common.stockage import StockagePrive


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
    # Une image PAS ENCORE PUBLIÉE — la photo d'un brouillon de page artiste —
    # ne vit pas dans la racine web : elle est écrite sous `MEDIA_PRIVE_ROOT`,
    # que Nginx n'expose pas, et servie par une vue qui contrôle les droits.
    # Cacher la page ne rend pas son image confidentielle, et une URL difficile
    # à deviner n'est pas un contrôle d'accès.
    #
    # Un média est dans l'un des deux états, jamais les deux : privé tant qu'il
    # n'est pas publié, public ensuite. Publier DÉPLACE le fichier.
    fichier_prive = models.ImageField(
        "fichier image (brouillon)",
        storage=StockagePrive,
        upload_to="brouillons/%Y/%m/",
        blank=True,
        editable=False,
    )
    # Dimensions et vignette sont DÉRIVÉES du fichier (cf. `services.py`) :
    # ni saisies ni modifiables à la main. Les dimensions servent à réserver la
    # place de l'image avant son arrivée (pas de saut de mise en page) ; la
    # vignette est proposée en `srcset` pour que le téléphone ne télécharge pas
    # une image de 2000 px dans une carte de 300.
    largeur = models.PositiveIntegerField("largeur (px)", null=True, blank=True, editable=False)
    hauteur = models.PositiveIntegerField("hauteur (px)", null=True, blank=True, editable=False)
    vignette = models.ImageField(
        "vignette",
        upload_to="medias/vignettes/%Y/%m/",
        blank=True,
        editable=False,
    )
    vignette_largeur = models.PositiveIntegerField(null=True, blank=True, editable=False)
    vignette_hauteur = models.PositiveIntegerField(null=True, blank=True, editable=False)
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

    @property
    def est_prive(self) -> bool:
        """Vrai si l'image n'est pas encore publiée, donc pas servie par Nginx."""
        return bool(self.fichier_prive)

    @property
    def image(self):
        """Le fichier image de ce média, public ou privé — celui qui existe.

        Les traitements (réduction, dimensions) passent par là ; l'affichage,
        lui, doit distinguer les deux, puisqu'un fichier privé n'a pas d'URL.
        """
        return self.fichier_prive if self.est_prive else self.fichier

    @property
    def a_une_image(self) -> bool:
        """Vrai si le média porte une image, publiée ou non.

        Les gabarits publics testent `media.fichier` : un média privé y est donc
        écarté sans rien afficher, ce qui est le bon défaut. Les écrans qui ONT
        le droit de le montrer — l'édition et l'aperçu — testent celle-ci.
        """
        return bool(self.image)

    @classmethod
    def from_db(cls, db, field_names, values):
        """Mémorise le fichier TEL QU'IL EST EN BASE.

        S'il change, les dimensions et la vignette d'avant ne décrivent plus
        rien : `save` les jette pour que le traitement reparte de zéro."""
        instance = super().from_db(db, field_names, values)
        if "fichier" in field_names:
            instance._fichier_initial = instance.fichier.name
        return instance

    def save(self, *args, **kwargs):
        """Enregistre, puis prépare l'image (réduction + vignette).

        Le traitement vit ici plutôt que dans les cinq services qui créent des
        médias, plus l'admin : c'est le seul endroit que tous les chemins
        traversent. Il est silencieux sur un fichier absent ou illisible — un
        confort ne doit pas faire échouer un téléversement."""
        # Import local : `services` importe ce module (cycle sinon).
        from .services import preparer_media

        if self.fichier.name != getattr(self, "_fichier_initial", self.fichier.name):
            self.largeur = self.hauteur = None
            self.vignette_largeur = self.vignette_hauteur = None
            self.vignette.delete(save=False)
        super().save(*args, **kwargs)
        self._fichier_initial = self.fichier.name
        if preparer_media(self):
            super().save(
                update_fields=[
                    "largeur",
                    "hauteur",
                    "vignette",
                    "vignette_largeur",
                    "vignette_hauteur",
                ]
            )

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
