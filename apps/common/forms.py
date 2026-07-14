"""Briques transverses pour l'accessibilité des formulaires (cf. CLAUDE.md règle 9)."""

from __future__ import annotations


class AideAccessibleMixin:
    """Relie le texte d'aide de chaque champ à son widget via ``aria-describedby``.

    Un lecteur d'écran annonce alors l'aide quand l'utilisateur atteint le champ
    (WCAG 1.3.1 / 3.3.2), et pas seulement s'il la survole des yeux. L'id
    référencé est ``id_<champ>_aide`` : il doit être posé sur le
    ``<span class="champ__aide">`` correspondant dans le gabarit (sinon la
    référence est simplement ignorée).

    À placer **avant** la classe de formulaire de base (ex.
    ``class MonForm(AideAccessibleMixin, forms.ModelForm)``) pour que
    ``super().__init__`` ait déjà construit les champs.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom, champ in self.fields.items():
            if not champ.help_text:
                continue
            aide_id = f"id_{nom}_aide"
            existant = champ.widget.attrs.get("aria-describedby", "")
            champ.widget.attrs["aria-describedby"] = f"{existant} {aide_id}".strip()
