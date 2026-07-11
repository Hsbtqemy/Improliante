"""Formulaires du back-office."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.agenda.models import Evenement, Intervention
from apps.budget.models import (
    Adhesion,
    Categorie,
    RecuFiscal,
    Saison,
    SoldeTresorerie,
    Transaction,
)
from apps.coeur.models import Membre, ParametresAssociation, Signataire, Utilisateur
from apps.common.fiches import ImagesFicheFormMixin
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.gouvernance.models import Pouvoir, Presence, Resolution, Reunion, Sujet
from apps.spectacles.models import LigneDistribution, Spectacle

# Format des <input type="datetime-local"> (sans fuseau ni secondes).
_FORMATS_DATETIME_LOCAL = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


def _restreindre_signataires_actifs(form):
    """Limite le champ `signataire` aux signataires actifs (optionnel)."""
    champ = form.fields["signataire"]
    champ.queryset = Signataire.objects.filter(actif=True)
    champ.required = False


class RecuFiscalForm(forms.ModelForm):
    """Saisie / complément d'un reçu fiscal avant émission.

    Sert aussi bien à la saisie manuelle qu'au complément d'un reçu pré-rempli
    depuis une adhésion (le bureau ajoute notamment l'adresse du donateur,
    absente du modèle Membre mais obligatoire sur le Cerfa). Le formulaire ne
    fait que valider les données ; le numéro et le snapshot sont posés par le
    service `emettre_recu`.
    """

    class Meta:
        model = RecuFiscal
        fields = [
            "type_versement",
            "forme",
            "montant",
            "date_versement",
            "donateur_nom",
            "donateur_adresse",
            "donateur_code_postal",
            "donateur_ville",
            "signataire",
        ]
        widgets = {
            "date_versement": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_versement"].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)

    def clean_montant(self) -> Decimal:
        montant = self.cleaned_data["montant"]
        if montant is None or montant <= 0:
            raise forms.ValidationError("Le montant doit être strictement positif.")
        return montant


class ClientForm(forms.ModelForm):
    """Création / édition d'un client (destinataire de facture)."""

    class Meta:
        model = Client
        fields = [
            "nom",
            "adresse",
            "code_postal",
            "ville",
            "email",
            "telephone",
            "siret",
            "numero_tva",
        ]
        widgets = {"adresse": forms.Textarea(attrs={"rows": 2})}


class FactureForm(forms.ModelForm):
    """En-tête d'une facture. Numéro, date d'émission et statut sont posés par
    le service `valider_facture`, jamais saisis à la main."""

    class Meta:
        model = Facture
        fields = ["client", "objet", "date_echeance", "mentions_legales", "signataire"]
        widgets = {
            "date_echeance": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "mentions_legales": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_echeance"].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)


# Lignes d'une facture éditées en bloc avec l'en-tête (formset inline).
LigneFactureFormSet = forms.inlineformset_factory(
    Facture,
    LigneFacture,
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva"],
    extra=1,  # une seule ligne vide ; « + Ajouter une ligne » (JS) pour d'autres
    can_delete=True,
)


class DevisForm(forms.ModelForm):
    """En-tête d'un devis. Le numéro est attribué par le service (non saisi)."""

    class Meta:
        model = Devis
        fields = ["client", "objet", "date", "date_validite", "conditions", "signataire"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_validite": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "conditions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date", "date_validite"):
            self.fields[champ].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)


LigneDevisFormSet = forms.inlineformset_factory(
    Devis,
    LigneDevis,
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva"],
    extra=1,  # une seule ligne vide ; « + Ajouter une ligne » (JS) pour d'autres
    can_delete=True,
)


# --- Budget -----------------------------------------------------------------


class TransactionForm(forms.ModelForm):
    """Recette ou dépense, prévue ou réalisée, rattachée à une saison."""

    class Meta:
        model = Transaction
        fields = ["saison", "type_flux", "statut", "libelle", "montant", "date", "categorie"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]

    def clean_montant(self) -> Decimal:
        montant = self.cleaned_data["montant"]
        if montant is None or montant <= 0:
            raise forms.ValidationError("Le montant doit être strictement positif.")
        return montant


class SaisonForm(forms.ModelForm):
    class Meta:
        model = Saison
        fields = ["nom", "date_debut", "date_fin"]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date_debut", "date_fin"):
            self.fields[champ].input_formats = ["%Y-%m-%d"]


class SoldeTresorerieForm(forms.ModelForm):
    """Saisie du solde en banque de référence (dernier pointage)."""

    class Meta:
        model = SoldeTresorerie
        fields = ["montant", "date_pointage", "note"]
        widgets = {
            "date_pointage": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "note": forms.TextInput(attrs={"placeholder": "ex. d'après le relevé du mois"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_pointage"].input_formats = ["%Y-%m-%d"]


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ["nom", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


# --- Paramètres de l'association --------------------------------------------


class ParametresAssociationForm(forms.ModelForm):
    """Identité légale de l'association (en-tête des documents officiels)."""

    class Meta:
        model = ParametresAssociation
        fields = [
            "nom",
            "objet",
            "adresse",
            "code_postal",
            "ville",
            "numero_rna",
            "numero_siret",
            "article_cgi",
            "signataire_nom",
            "signataire_qualite",
            "iban",
            "bic",
            "mention_tva",
        ]
        widgets = {"objet": forms.Textarea(attrs={"rows": 2})}


# --- Gouvernance ------------------------------------------------------------


class ReunionForm(forms.ModelForm):
    class Meta:
        model = Reunion
        fields = ["titre", "type_reunion", "statut", "date", "lieu_texte", "convocation_texte"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "convocation_texte": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


class SujetOrdreDuJourForm(forms.ModelForm):
    """Ajout d'un sujet à l'ordre du jour d'une réunion (réunion posée par la vue)."""

    class Meta:
        model = Sujet
        fields = ["titre", "description", "priorite", "ordre_du_jour"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


def _membres_actifs():
    return Membre.objects.filter(actif=True)


class PresenceForm(forms.ModelForm):
    class Meta:
        model = Presence
        fields = ["membre", "statut", "peut_voter"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membre"].queryset = _membres_actifs()


class PouvoirForm(forms.ModelForm):
    class Meta:
        model = Pouvoir
        fields = ["mandant", "mandataire"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mandant"].queryset = _membres_actifs()
        self.fields["mandataire"].queryset = _membres_actifs()

    def clean(self):
        donnees = super().clean()
        if donnees.get("mandant") and donnees.get("mandant") == donnees.get("mandataire"):
            raise forms.ValidationError("Le mandant et le mandataire doivent être différents.")
        return donnees


class ResolutionForm(forms.ModelForm):
    class Meta:
        model = Resolution
        fields = [
            "intitule",
            "texte",
            "type_majorite",
            "sujet",
            "nombre_pour",
            "nombre_contre",
            "nombre_abstention",
            "ordre",
        ]
        widgets = {"texte": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, reunion=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ne proposer que les sujets de cette réunion comme rattachement.
        if reunion is not None:
            self.fields["sujet"].queryset = reunion.sujets.all()
        self.fields["sujet"].required = False


class MembreForm(forms.ModelForm):
    """Fiche d'une personne (adhérent / membre), pour la création et l'édition.

    L'identité vit sur la fiche ; le compte de connexion est facultatif. À la
    création, cocher « ouvrir un accès » crée le compte et le lien d'activation
    (le membre y choisit son mot de passe). En édition, l'ouverture d'accès passe
    par un bouton dédié : la case est retirée."""

    ouvrir_acces = forms.BooleanField(
        label="Ouvrir un accès en ligne maintenant",
        required=False,
        help_text="Crée un compte de connexion et un lien d'activation. Nécessite un e-mail.",
    )

    class Meta:
        model = Membre
        fields = ["prenom", "nom", "email", "telephone", "role_public"]

    def __init__(self, *args, edition=False, **kwargs):
        super().__init__(*args, **kwargs)
        if edition:
            self.fields.pop("ouvrir_acces")

    def clean_email(self) -> str:
        # L'e-mail sert d'identifiant de connexion : on le canonise en minuscules.
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        donnees = super().clean()
        if donnees.get("ouvrir_acces"):
            email = donnees.get("email", "")
            if not email:
                self.add_error("email", "Un e-mail est nécessaire pour ouvrir un accès.")
            elif Utilisateur.objects.filter(username__iexact=email).exists():
                self.add_error("email", "Un compte existe déjà avec cet e-mail.")
        return donnees


class MembreRapideForm(forms.ModelForm):
    """Création express d'une personne (sans compte) depuis l'écran Adhésions."""

    class Meta:
        model = Membre
        fields = ["prenom", "nom", "email"]

    def clean_email(self) -> str:
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        donnees = super().clean()
        if not (donnees.get("prenom") or donnees.get("nom")):
            raise forms.ValidationError("Indiquez au moins un prénom ou un nom.")
        return donnees


class AdhesionForm(forms.ModelForm):
    """Adhésion d'une personne pour une saison (statut + montants attendu/versé)."""

    class Meta:
        model = Adhesion
        fields = ["membre", "saison", "statut", "montant_attendu", "montant_verse", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, membre_optionnel=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]
        if membre_optionnel:
            # Création à la volée possible : la personne peut être créée dans la
            # foulée, donc « membre » n'est pas obligatoire ici (arbitré en vue).
            self.fields["membre"].required = False

    def clean_montant_attendu(self) -> Decimal:
        return self._montant_positif_ou_nul("montant_attendu")

    def clean_montant_verse(self) -> Decimal:
        return self._montant_positif_ou_nul("montant_verse")

    def _montant_positif_ou_nul(self, champ) -> Decimal:
        montant = self.cleaned_data.get(champ)
        if montant is not None and montant < 0:
            raise forms.ValidationError("Le montant ne peut pas être négatif.")
        return montant


# --- Programmation : événements & projets (gestion directe par le bureau) ----


class EvenementBureauForm(ImagesFicheFormMixin, forms.ModelForm):
    """Création / édition d'un événement par le bureau.

    Superset du formulaire membre : expose en plus `visibilite`, le `lieu` (fiche)
    et un `spectacle` non restreint aux projets d'un membre. Le statut de
    modération est piloté par les boutons de la vue (« Publier » / « brouillon »)."""

    class Meta:
        model = Evenement
        fields = [
            "titre",
            "description",
            "date_debut",
            "date_fin",
            "lieu",
            "lieu_texte",
            "visibilite",
            "spectacle",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "date_debut": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "date_fin": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date_debut", "date_fin"):
            self.fields[champ].input_formats = _FORMATS_DATETIME_LOCAL
        self.fields["spectacle"].required = False
        self.fields["lieu"].required = False


class ProjetBureauForm(ImagesFicheFormMixin, forms.ModelForm):
    """Création / édition d'un projet/spectacle par le bureau.

    Superset du formulaire membre : `type_portage` complet (dont « association »)
    et `porteurs`. La mise en scène se saisit comme une ligne de distribution
    (rôle libre), pas comme un champ dédié. Statut de modération piloté par la vue."""

    class Meta:
        model = Spectacle
        fields = [
            "titre",
            "synopsis",
            "note_intention",
            "type_portage",
            "statut_projet",
            "genre",
            "public_vise",
            "duree_minutes",
            "porteurs",
        ]
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 4}),
            "note_intention": forms.Textarea(attrs={"rows": 4}),
            # Cases à cocher plutôt que le <select multiple> par défaut : ajout /
            # retrait évidents, accessible et confortable sur mobile.
            "porteurs": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["porteurs"].required = False


# Intervenants d'un événement (membre + rôle) et distribution d'un projet
# (membre OU nom externe + rôle) — édités via formsets inline, comme les lignes
# de facture. La validation modèle (unicité / « membre XOR nom_externe ») remonte.
InterventionFormSet = forms.inlineformset_factory(
    Evenement, Intervention, fields=["membre", "role"], extra=1, can_delete=True
)
LigneDistributionFormSet = forms.inlineformset_factory(
    Spectacle, LigneDistribution, fields=["membre", "nom_externe", "role"], extra=1, can_delete=True
)
