"""Formulaires du front public."""

from __future__ import annotations

from django import forms


class ContactForm(forms.Form):
    """Formulaire de contact : consentement RGPD obligatoire + piège anti-spam."""

    nom = forms.CharField(max_length=200, label="Votre nom")
    email = forms.EmailField(label="Votre e-mail")
    sujet = forms.CharField(max_length=200, required=False, label="Sujet")
    message = forms.CharField(widget=forms.Textarea, label="Votre message")
    consentement = forms.BooleanField(
        required=True,
        label="J'accepte que mes données soient traitées pour répondre à ma demande.",
    )
    # Champ piège anti-spam : masqué, ne doit jamais être rempli par un humain.
    site_web = forms.CharField(
        required=False,
        label="Ne pas remplir",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )

    def clean_site_web(self) -> str:
        if self.cleaned_data.get("site_web"):
            raise forms.ValidationError("Spam détecté.")
        return ""
