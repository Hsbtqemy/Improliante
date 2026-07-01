"""Formulaires de l'espace membre."""

from __future__ import annotations

from django import forms

from apps.agenda.models import Evenement
from apps.spectacles.models import Spectacle

# Format des <input type="datetime-local"> (sans fuseau ni secondes).
_FORMATS_DATETIME_LOCAL = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


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


class EvenementMembreForm(forms.ModelForm):
    """Proposition / édition par un membre d'un événement d'agenda.

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
