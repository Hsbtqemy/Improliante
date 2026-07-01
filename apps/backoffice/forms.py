"""Formulaires du back-office."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.budget.models import RecuFiscal
from apps.coeur.models import Signataire
from apps.documents.models import Document, Dossier
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture


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
    extra=1,
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
    extra=1,
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
