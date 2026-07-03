"""Formulaires du back-office."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.budget.models import Categorie, RecuFiscal, Saison, Transaction
from apps.coeur.models import Membre, ParametresAssociation, Signataire, Utilisateur
from apps.documents.models import Document, Dossier
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.gouvernance.models import Pouvoir, Presence, Resolution, Reunion, Sujet


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
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva", "ordre"],
    extra=4,  # plusieurs lignes vides d'emblée (utilisable même sans JavaScript)
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
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva", "ordre"],
    extra=4,  # plusieurs lignes vides d'emblée (utilisable même sans JavaScript)
    can_delete=True,
)


# --- GED --------------------------------------------------------------------


class DossierForm(forms.ModelForm):
    """Création d'un dossier (le parent est fourni par la vue, pas ici)."""

    class Meta:
        model = Dossier
        fields = ["nom", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class DocumentForm(forms.ModelForm):
    """Téléversement d'un document (le dossier et l'auteur sont posés par la vue)."""

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


class NouvelleVersionForm(forms.Form):
    """Remplacement d'un document par une nouvelle version (fichier seul)."""

    fichier = forms.FileField(label="Nouveau fichier")


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


class MembreCreationForm(forms.Form):
    """Création d'un compte membre par le bureau (Utilisateur + Membre).

    L'e-mail sert d'identifiant de connexion : il doit être unique. Le mot de
    passe n'est PAS saisi ici — le membre le définit via un lien d'activation
    (cf. `apps.coeur.services`). Formulaire volontairement `forms.Form` (et non
    ModelForm) car il couvre deux modèles."""

    prenom = forms.CharField(label="Prénom", max_length=150)
    nom = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(
        label="E-mail",
        help_text="Sert d'identifiant de connexion. Doit être unique.",
    )
    role_public = forms.CharField(
        label="Rôle public",
        max_length=200,
        required=False,
        help_text="Ex. « Comédienne, mise en scène » — affiché sur la fiche publique si visible.",
    )
    telephone = forms.CharField(label="Téléphone", max_length=32, required=False)

    def clean_email(self) -> str:
        # Normalisation en minuscules : l'e-mail sert d'identifiant, on évite
        # les doublons ne différant que par la casse et on canonise le stockage.
        email = self.cleaned_data["email"].strip().lower()
        # L'e-mail est aussi l'identifiant (username) : on vérifie les deux.
        existe = Utilisateur.objects.filter(username__iexact=email).exists() or (
            Utilisateur.objects.filter(email__iexact=email).exists()
        )
        if existe:
            raise forms.ValidationError("Un compte existe déjà avec cet e-mail.")
        return email
