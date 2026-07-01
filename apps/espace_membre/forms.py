"""Formulaires de l'espace membre."""

from __future__ import annotations

from django import forms

from apps.spectacles.models import Spectacle


class ProjetMembreForm(forms.ModelForm):
    """Édition par un membre de la fiche de SON projet (perso ou collectif).

    Ne sont exposés que les champs descriptifs. La modération, la traçabilité
    (`cree_par`, `valide_par`) et le rattachement aux `porteurs` sont pilotés
    par la vue, jamais par l'utilisateur. Le `type_portage` est restreint à
    « personnel » / « collectif » : un membre ne peut pas estampiller son
    projet comme une production de l'association.
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
