"""Contexte de gabarit commun au back-office."""

from __future__ import annotations

from apps.coeur.roles import est_bureau


def roles(request):
    """Expose `est_bureau` aux gabarits (affichage conditionnel du back-office)."""
    return {"est_bureau": est_bureau(request.user)}
