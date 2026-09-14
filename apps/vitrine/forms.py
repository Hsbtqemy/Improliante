"""Formulaires du front public."""

from __future__ import annotations

from django import forms
from django.conf import settings


class ContactForm(forms.Form):
    """Formulaire de contact : consentement RGPD obligatoire + piège anti-spam."""

    nom = forms.CharField(max_length=200, label="Votre nom")
    email = forms.EmailField(label="Votre e-mail")
    sujet = forms.CharField(max_length=200, required=False, label="Sujet")
    # Sans borne, le champ est une zone de dépôt — l'audit le relevait comme
    # « pas de longueur métier explicite ». La valeur est large : elle arrête
    # le versement d'un fichier, pas une longue demande.
    #
    # Lue à l'IMPORT, comme la plupart des réglages : elle change au
    # redémarrage, pas à chaud. Le dire ici parce qu'un test l'avait cru
    # modifiable en cours de route et posait une valeur que personne ne lisait.
    message = forms.CharField(
        widget=forms.Textarea,
        label="Votre message",
        max_length=settings.LONGUEUR_MAX_MESSAGE,
    )
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


class InscriptionEvenementForm(forms.Form):
    """Réservation de places par un visiteur, sans compte.

    Même précautions que le formulaire de contact — consentement explicite et
    piège anti-spam — parce que c'est la même exposition : un formulaire ouvert
    sur Internet qui écrit en base. `places` est borné côté serveur : une jauge
    ne protège de rien si l'on peut réclamer mille places d'un coup."""

    nom = forms.CharField(max_length=200, label="Votre nom")
    email = forms.EmailField(
        label="Votre e-mail",
        # Ne rien promettre qu'on n'envoie : aucun message n'est expédié pour
        # l'instant (l'envoi bute sur le même mur que VIT-1, celui d'une IP
        # neuve). L'adresse sert à l'association le jour du spectacle.
        help_text="Permet à l'association de vous joindre en cas de changement.",
    )
    places = forms.IntegerField(
        label="Nombre de places",
        min_value=1,
        max_value=10,
        initial=1,
        help_text="Dix places au maximum par réservation.",
    )
    consentement = forms.BooleanField(
        required=True,
        label=(
            "J'accepte que mon nom et mon e-mail soient conservés pour gérer cette réservation."
        ),
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
