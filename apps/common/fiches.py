"""Briques partagées pour la gestion des « fiches » à images (projets, événements).

Mutualisé entre l'espace membre et le back-office : le mixin de formulaire (affiche
+ galerie, `alt` obligatoire) et l'orchestration `appliquer_images` qui délègue aux
services du domaine (`apps.agenda.services` / `apps.spectacles.services`).
"""

from __future__ import annotations

from django import forms

# Taille maximale d'une image téléversée (5 Mio). Le type « réel » est validé
# par `ImageField` (Pillow décode le fichier) ; on borne ici le poids.
TAILLE_MAX_IMAGE = 5 * 1024 * 1024


class ImagesFicheFormMixin(forms.Form):
    """Champs et validations communs pour gérer l'affiche + la galerie d'une
    fiche (projet ou événement).

    Les images ne sont pas des champs du modèle : elles créent des `Media`
    (avec `alt` OBLIGATOIRE, accessibilité) traités par la vue via le service
    du domaine. L'affiche peut être remplacée ou retirée ; on n'ajoute qu'une
    image de galerie à la fois (une par soumission), ce qui garantit un `alt`
    par image. La suppression d'images existantes se fait par cases à cocher
    lues directement dans la vue (liste dynamique), bornées à la fiche éditée.
    """

    affiche_fichier = forms.ImageField(
        label="Affiche (image principale)",
        required=False,
        help_text="Image mise en avant sur la fiche publique (JPG/PNG).",
    )
    affiche_alt = forms.CharField(
        label="Texte alternatif de l'affiche",
        required=False,
        max_length=255,
        help_text="Décrit l'affiche pour les lecteurs d'écran (obligatoire si vous ajoutez une affiche).",
    )
    retirer_affiche = forms.BooleanField(label="Retirer l'affiche actuelle", required=False)

    galerie_fichier = forms.ImageField(
        label="Ajouter une image à la galerie",
        required=False,
    )
    galerie_alt = forms.CharField(
        label="Texte alternatif de cette image",
        required=False,
        max_length=255,
        help_text="Obligatoire si vous ajoutez une image.",
    )

    def champs_descriptifs(self):
        """Champs textuels du modèle, pour un rendu séparé des champs image."""
        return [self[nom] for nom in self.Meta.fields]

    def champ_affiche(self):
        """Champs de saisie de l'affiche (fichier + alt) pour le template."""
        return [self["affiche_fichier"], self["affiche_alt"]]

    def champ_galerie(self):
        """Champs d'ajout d'une image de galerie (fichier + alt)."""
        return [self["galerie_fichier"], self["galerie_alt"]]

    @staticmethod
    def _valider_taille(fichier) -> None:
        if fichier and fichier.size > TAILLE_MAX_IMAGE:
            raise forms.ValidationError("Image trop volumineuse (5 Mio maximum).")

    def clean_affiche_fichier(self):
        fichier = self.cleaned_data.get("affiche_fichier")
        self._valider_taille(fichier)
        return fichier

    def clean_galerie_fichier(self):
        fichier = self.cleaned_data.get("galerie_fichier")
        self._valider_taille(fichier)
        return fichier

    def clean(self):
        """`alt` obligatoire dès qu'une image est fournie (accessibilité)."""
        cleaned = super().clean()
        if cleaned.get("affiche_fichier") and not (cleaned.get("affiche_alt") or "").strip():
            self.add_error("affiche_alt", "Le texte alternatif de l'affiche est obligatoire.")
        if cleaned.get("galerie_fichier") and not (cleaned.get("galerie_alt") or "").strip():
            self.add_error("galerie_alt", "Le texte alternatif de l'image est obligatoire.")
        return cleaned


def appliquer_images(fiche, form, request, service):
    """Applique à la fiche (projet ou événement) les opérations d'images.

    `service` est le module du domaine (`spectacles.services` ou
    `agenda.services`) exposant `definir_affiche`, `retirer_affiche`,
    `ajouter_image_galerie` et `retirer_images_galerie`.

    Affiche : remplacée si un fichier est fourni, sinon retirée si la case est
    cochée. Galerie : ajout d'une image (si fournie) puis retrait des images
    cochées. Le retrait est borné à la fiche côté service (anti-IDOR)."""
    donnees = form.cleaned_data
    if donnees.get("affiche_fichier"):
        service.definir_affiche(
            fiche, donnees["affiche_fichier"], donnees["affiche_alt"], cree_par=request.user
        )
    elif donnees.get("retirer_affiche"):
        service.retirer_affiche(fiche)

    if donnees.get("galerie_fichier"):
        service.ajouter_image_galerie(
            fiche, donnees["galerie_fichier"], donnees["galerie_alt"], cree_par=request.user
        )

    a_retirer = [i for i in request.POST.getlist("supprimer_image") if i.isdigit()]
    if a_retirer:
        service.retirer_images_galerie(fiche, a_retirer)
