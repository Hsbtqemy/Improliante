"""Construction de la grille mensuelle du calendrier public."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from django.utils import timezone


def bornes_grille(annee: int, mois: int) -> tuple[date, date]:
    """Premier et dernier jour affichés dans la grille du mois (débordements inclus)."""
    semaines = calendar.Calendar(firstweekday=0).monthdatescalendar(annee, mois)
    return semaines[0][0], semaines[-1][-1]


def construire_calendrier(annee: int, mois: int, evenements) -> list[list[dict]]:
    """Grille du mois : liste de semaines, chaque semaine = 7 jours.

    Chaque jour est un dict ``{date, dans_le_mois, evenements}``. Les jours de
    débordement (mois voisins) complètent les semaines.
    """
    semaines_dates = calendar.Calendar(firstweekday=0).monthdatescalendar(annee, mois)
    par_jour: dict[date, list] = defaultdict(list)
    for evenement in evenements:
        jour = timezone.localtime(evenement.date_debut).date()
        par_jour[jour].append(evenement)

    return [
        [
            {
                "date": jour,
                "dans_le_mois": jour.month == mois,
                "evenements": par_jour.get(jour, []),
            }
            for jour in semaine
        ]
        for semaine in semaines_dates
    ]
