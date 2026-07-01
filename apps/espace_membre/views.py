"""Vues de l'espace membre connecté.

Règle anti-IDOR (NON NÉGOCIABLE) : chaque écran filtre selon
`request.user.membre`, jamais selon un identifiant fourni dans l'URL.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def tableau_de_bord(request):
    """Accueil de l'espace membre : rappel de l'adhésion du membre connecté."""
    # RelatedObjectDoesNotExist hérite d'AttributeError : getattr renvoie None
    # proprement si le compte n'a pas de fiche membre (ex. compte technique).
    membre = getattr(request.user, "membre", None)
    adhesions = []
    if membre is not None:
        adhesions = membre.adhesions.select_related("saison").order_by("-saison__date_debut")
    return render(
        request,
        "espace_membre/tableau_de_bord.html",
        {"membre": membre, "adhesions": adhesions},
    )
