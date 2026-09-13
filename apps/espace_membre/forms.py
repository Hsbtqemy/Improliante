"""Formulaires de l'espace membre."""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import PasswordResetForm, _unicode_ci_compare
from django.forms import inlineformset_factory

from apps.agenda.models import Evenement
from apps.coeur.models import BrouillonPageArtiste, LienReseau, Membre, Utilisateur
from apps.common.fiches import TAILLE_MAX_IMAGE, ImagesFicheFormMixin
from apps.documents.models import Document, Dossier
from apps.documents.validators import valider_fichier_document
from apps.gouvernance.models import Presence
from apps.spectacles.models import Spectacle

# Format des <input type="datetime-local"> (sans fuseau ni secondes).
_FORMATS_DATETIME_LOCAL = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


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


class PageArtisteForm(forms.ModelForm):
    """Édition par un membre de SA page publique — dans son **brouillon**.

    Rien de ce qui est saisi ici ne part en ligne à l'enregistrement : le public
    lit le `Membre`, ce formulaire écrit le `BrouillonPageArtiste`. C'est la
    vue qui, sur le geste « Publier », recopie l'un sur l'autre.

    Ce que ce formulaire ne couvre PAS, et qui part donc en ligne tout de suite :
    le téléphone (qui n'est pas public) et les réseaux sociaux, gérés à part par
    `CoordonneesForm` et `LienReseauFormSet`. L'écran le dit à côté du geste.

    La photo crée un `Media` (alt obligatoire) traité par la vue via
    `apps.coeur.services`.
    """

    photo_fichier = forms.ImageField(
        label="Photo (portrait)",
        required=False,
        help_text="Affichée sur votre fiche publique une fois publiée (JPG/PNG).",
    )
    photo_alt = forms.CharField(
        label="Description de la photo",
        required=False,
        max_length=255,
        help_text="Obligatoire si vous ajoutez une photo (accessibilité).",
    )
    retirer_photo = forms.BooleanField(label="Retirer la photo actuelle", required=False)

    class Meta:
        model = BrouillonPageArtiste
        fields = ["role_public", "bio", "site_web"]
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


class CoordonneesForm(forms.ModelForm):
    """Ce qui n'est pas public et n'a donc rien à publier : le téléphone.

    Enregistré tout de suite, sans passer par le brouillon — une coordonnée que
    le site n'affiche pas n'a pas de « version publique » à protéger.
    """

    class Meta:
        model = Membre
        fields = ["telephone"]


class LienReseauForm(forms.ModelForm):
    """Une ligne de la liste « réseaux sociaux ».

    « Adresse » se lisait comme une adresse postale ou un courriel : on nomme et
    on illustre ce qui est attendu, l'URL publique du profil.

    L'aide se relie au champ toute seule : Django pose `aria-describedby` vers
    `<auto_id>_helptext`, et `auto_id` porte déjà le préfixe de la ligne
    (`id_liens-0-url`), donc la référence est unique par ligne sans rien écrire
    ici. Un `aria-describedby` posé à la main désactiverait justement ce calcul
    (`BoundField.aria_describedby` s'efface devant un attribut de widget) et
    perdrait au passage le rattachement du message d'erreur."""

    class Meta:
        model = LienReseau
        fields = ["reseau", "url", "libelle", "ordre"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["url"].widget.attrs["placeholder"] = "https://www.instagram.com/mon-compte/"


# Réseaux sociaux : liste flexible éditable en une fois (ajout / suppression).
LienReseauFormSet = inlineformset_factory(
    Membre,
    LienReseau,
    form=LienReseauForm,
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


class _ChampDossierArborescent(forms.ModelChoiceField):
    """Liste de dossiers qui laisse voir l'arborescence.

    Un `<select>` de noms nus devient ambigu dès qu'un arbre porte deux
    « 2025 » : on choisit une destination sans savoir laquelle. Les cibles
    arrivant triées par chemin, une indentation par profondeur suffit à rendre
    la structure lisible — sans composant ni script."""

    def label_from_instance(self, obj):
        indentation = "\u00a0\u00a0\u00a0\u00a0" * (obj.depth - 1)
        # Dans l'espace personnel, la destination DÉCIDE de la confidentialité
        # du dossier déplacé. La taire jusqu'à l'encart général reviendrait à
        # faire choisir à l'aveugle entre « partagé avec la troupe » et
        # « transmis au bureau » — deux audiences très différentes.
        if obj.espace == Dossier.Espace.PERSO:
            return f"{indentation}{obj.nom} — {obj.get_visibilite_display()}"
        return f"{indentation}{obj.nom}"


class DeplacerDossierForm(forms.Form):
    """Choix du dossier d'accueil, ou de la racine.

    Les cibles proposées sont calculées par la vue : même espace, même
    propriétaire pour un dossier personnel, et jamais le dossier lui-même ni
    l'un de ses sous-dossiers. Le champ n'est donc pas seulement une commodité
    d'affichage — c'est la **première** barrière, doublée par les invariants
    que `documents.services.deplacer_dossier` refait valoir de son côté."""

    parent = _ChampDossierArborescent(
        queryset=Dossier.objects.none(),
        required=False,
        label="Ranger dans",
        empty_label="— À la racine —",
        help_text="Laisser vide pour sortir le dossier de son parent actuel.",
    )

    def __init__(self, *args, cibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cibles is not None:
            self.fields["parent"].queryset = cibles


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


class DocumentAssociationForm(forms.ModelForm):
    """Téléversement d'un document dans la branche Association (bureau).

    Contrairement à la branche perso/partagé, l'audience est portée par le
    **document** : le bureau fixe la `confidentialite` (tout compte connecté /
    membres / privé) et une éventuelle date de validité. Aucun de ces niveaux
    n'ouvre au visiteur — le plus large s'arrête à la connexion."""

    class Meta:
        model = Document
        fields = ["titre", "fichier", "confidentialite", "description", "date_validite"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "date_validite": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_validite"].input_formats = ["%Y-%m-%d"]
        # Un document officiel est destiné aux membres par défaut (CR d'AG,
        # statuts, bilan…) ; le bureau élargit ou restreint au besoin.
        self.fields["confidentialite"].initial = Document.Confidentialite.MEMBRES

    def clean_fichier(self):
        return valider_fichier_document(self.cleaned_data.get("fichier"))


class NouvelleVersionForm(forms.Form):
    """Remplacement d'un document par une nouvelle version (fichier seul)."""

    fichier = forms.FileField(label="Nouveau fichier")

    def clean_fichier(self):
        return valider_fichier_document(self.cleaned_data.get("fichier"))


class ReponseConvocationForm(forms.Form):
    """Réponse d'un membre à une convocation d'AG : présence ou pouvoir.

    Les trois choix proposés au membre (« excusé » reste une décision du
    secrétaire pour le PV, hors libre-service). Le mandataire n'est requis que
    si le membre choisit de donner pouvoir."""

    CHOIX_STATUT = [
        (Presence.Statut.PRESENT, "Je serai présent·e"),
        (Presence.Statut.ABSENT, "Je ne pourrai pas être présent·e"),
        (Presence.Statut.REPRESENTE, "Je donne pouvoir à…"),
    ]

    statut = forms.ChoiceField(
        choices=CHOIX_STATUT, widget=forms.RadioSelect, label="Votre réponse"
    )
    mandataire = forms.ModelChoiceField(
        queryset=Membre.objects.none(),
        required=False,
        label="À qui donnez-vous pouvoir ?",
    )

    def __init__(self, *args, membre=None, **kwargs):
        super().__init__(*args, **kwargs)
        autres = Membre.objects.filter(actif=True)
        if membre is not None:
            autres = autres.exclude(pk=membre.pk)
        self.fields["mandataire"].queryset = autres

    def clean(self):
        donnees = super().clean()
        if donnees.get("statut") == Presence.Statut.REPRESENTE and not donnees.get("mandataire"):
            self.add_error("mandataire", "Choisissez le membre à qui vous donnez pouvoir.")
        return donnees


class MotDePasseOublieForm(PasswordResetForm):
    """Demande de réinitialisation, ouverte aussi aux comptes jamais activés.

    `PasswordResetForm.get_users` de Django écarte les comptes dont le mot de
    passe est INUTILISABLE. C'est le bon défaut là où « inutilisable » signifie
    « ce compte s'authentifie ailleurs » (LDAP, fournisseur externe) : lui
    envoyer un lien local ne mènerait à rien.

    Ici, il signifie l'inverse. `apps.coeur.services.ouvrir_compte` pose un mot
    de passe inutilisable **exprès** : le bureau ouvre l'accès, et le membre
    choisit son mot de passe lui-même par le lien d'activation. La personne la
    plus susceptible d'avoir oublié le sien est donc celle qui n'en a jamais
    défini — invitée il y a six mois, lien d'activation perdu — et le défaut de
    Django lui répondait par le silence, sur une page lui affirmant qu'un
    courriel était parti.

    Le jeton, lui, fonctionne dans les deux cas : `default_token_generator` le
    dérive du hachage stocké, et un mot de passe inutilisable en est un
    (`!` suivi d'aléa). Poser un mot de passe par ce chemin revient exactement à
    l'activation, jeton d'usage unique compris.

    `_unicode_ci_compare` est un nom privé de Django, importé sciemment : le
    réécrire ici le figerait au comportement d'aujourd'hui, alors qu'il porte un
    correctif de sécurité et peut être affiné en amont. La contrepartie est une
    montée de version de Django à surveiller — le test du parcours complet la
    verrait casser.
    """

    def get_users(self, email):
        # On retire UNIQUEMENT le filtre sur le mot de passe utilisable. Les
        # deux autres garde-fous de Django restent, et ce ne sont pas des
        # détails : `is_active` (un compte désactivé par le bureau ne se rouvre
        # pas tout seul par un courriel) et `_unicode_ci_compare`, qui reprend
        # la comparaison en Python parce que le `iexact` de la base peut, selon
        # sa collation, rapprocher deux adresses Unicode distinctes — et
        # enverrait alors le lien au mauvais compte.
        actifs = Utilisateur.objects.filter(email__iexact=email, is_active=True)
        return (u for u in actifs if _unicode_ci_compare(email, u.email))
