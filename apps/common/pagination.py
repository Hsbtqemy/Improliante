"""Pagination partagée par le back-office et le front public.

Une seule fonction, mais deux faces l'appellent : la garder dans les vues du
bureau obligeait le front à réinventer la tolérance aux numéros de page
farfelus, ou à importer le back-office depuis la vitrine.
"""

from __future__ import annotations

from django.core.paginator import Paginator


def paginer(request, objets, par_page=20):
    """Retourne la page demandée (`?page=N`) d'un queryset.

    `get_page` tolère un numéro absent, non numérique ou hors bornes (renvoie
    la 1re ou la dernière page) — pas d'erreur 500 sur `?page=abc`."""
    return Paginator(objets, par_page).get_page(request.GET.get("page"))
