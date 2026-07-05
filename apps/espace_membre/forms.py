"""Formulaires de l'espace membre."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from apps.agenda.models import Evenement
from apps.coeur.models import LienReseau, Membre
from apps.documents.models import Document, Dossier
from apps.documents.validators import valider_fichier_document
from apps.spectacles.models import Spectacle

# Format des <input type="datetime-local"> (sans fuseau ni secondes).
_FORMATS_DATETIME_LOCAL = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]

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


class ProjetMembreForm(ImagesFicheFormMixin, forms.ModelForm):
    """Édition par un membre de la fiche de SON projet (perso ou collectif).

    Champs descriptifs + gestion des images (affiche et galerie, via le mixin).
    La modération, la traçabilité (`cree_par`, `valide_par`) et le rattachement
    aux `porteurs` sont pilotés par la vue, jamais par l'utilisateur. Le
    `type_portage` est restreint à « personnel » / « collectif » : un membre ne
    peut pas estampiller son projet comme une production de l'association.
    """

    class Meta:
        model = Spectacle
        fields = [
            "titre",
            "type_portage",
            "synopsis",
            "note_intention",
            "statut_projet",
            "genre",
            "public_vise",
            "duree_minutes",
        ]
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 4}),
            "note_intention": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        portages_autorises = {
            Spectacle.TypePortage.PERSONNEL,
            Spectacle.TypePortage.COLLECTIF,
        }
        self.fields["type_portage"].choices = [
            (valeur, libelle)
            for valeur, libelle in Spectacle.TypePortage.choices
            if valeur in portages_autorises
        ]
        self.fields["type_portage"].initial = Spectacle.TypePortage.PERSONNEL


class EvenementMembreForm(ImagesFicheFormMixin, forms.ModelForm):
    """Proposition / édition par un membre d'un événement d'agenda.

    Champs descriptifs + gestion des images (affiche et galerie, via le mixin).
    La `visibilite` n'est PAS exposée : le bureau la fixe à la validation
    (cf. modèle `Evenement`). Le champ `spectacle` est restreint aux projets
    portés par le membre — anti-IDOR au niveau du champ : on ne peut pas
    rattacher son événement à la création d'un autre. Un lien déjà posé par le
    bureau vers un autre spectacle est toutefois conservé (pas d'effacement
    silencieux à l'édition).
    """

    class Meta:
        model = Evenement
        fields = ["titre", "description", "date_debut", "date_fin", "lieu_texte", "spectacle"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "date_debut": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "date_fin": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, membre=None, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date_debut", "date_fin"):
            self.fields[champ].input_formats = _FORMATS_DATETIME_LOCAL

        projets = (
            Spectacle.objects.filter(porteurs=membre)
            if membre is not None
            else Spectacle.objects.none()
        )
        # Conserve un rattachement existant même s'il sort du périmètre du membre.
        if self.instance.pk and self.instance.spectacle_id:
            projets = (projets | Spectacle.objects.filter(pk=self.instance.spectacle_id)).distinct()
        self.fields["spectacle"].queryset = projets
        self.fields["spectacle"].required = False


class ProfilMembreForm(forms.ModelForm):
    """Édition par un membre de SA propre fiche (bio, rôle public, coordonnées,
    site web, photo). Les réseaux sociaux sont gérés à part via un formset
    (`LienReseauFormSet`). La photo crée un `Media` (alt obligatoire) traité par
    la vue via `apps.coeur.services`."""

    photo_fichier = forms.ImageField(
        label="Photo (portrait)",
        required=False,
        help_text="Affichée sur votre fiche publique (JPG/PNG).",
    )
    photo_alt = forms.CharField(
        label="Description de la photo",
        required=False,
        max_length=255,
        help_text="Obligatoire si vous ajoutez une photo (accessibilité).",
    )
    retirer_photo = forms.BooleanField(label="Retirer la photo actuelle", required=False)

    class Meta:
        model = Membre
        fields = ["role_public", "bio", "telephone", "site_web"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 5})}

    def clean_photo_fichier(self):
        fichier = self.cleaned_data.get("photo_fichier")
        if fichier and fichier.size > TAILLE_MAX_IMAGE:
            raise forms.ValidationError("Image trop volumineuse (5 Mio maximum).")
        return fichier

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("photo_fichier") and not (cleaned.get("photo_alt") or "").strip():
            self.add_error("photo_alt", "La description de la photo est obligatoire.")
        return cleaned

    def champs_profil(self):
        """Champs texte du modèle, pour un rendu séparé des champs photo."""
        return [self[nom] for nom in self.Meta.fields]

    def champ_photo(self):
        return [self["photo_fichier"], self["photo_alt"]]


# Réseaux sociaux : liste flexible éditable en une fois (ajout / suppression).
LienReseauFormSet = inlineformset_factory(
    Membre,
    LienReseau,
    fields=["reseau", "url", "libelle", "ordre"],
    extra=1,
    can_delete=True,
)


class DossierCommunForm(forms.ModelForm):
    """Création / édition d'un dossier de fichiers (nom + description).

    La branche (Perso / Partagé / Bureau) est décidée par la vue selon l'action,
    pas par un champ du formulaire."""

    class Meta:
        model = Dossier
        fields = ["nom", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class DocumentMembreForm(forms.ModelForm):
    """Téléversement d'un fichier par un membre (le dossier et l'auteur sont
    posés par la vue ; l'audience est portée par le dossier, pas par le
    document → pas de champ `confidentialite`)."""

    class Meta:
        model = Document
        fields = ["titre", "fichier", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean_fichier(self):
        return valider_fichier_document(self.cleaned_data.get("fichier"))
