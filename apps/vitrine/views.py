"""Vues du front public (« vitrine »).

Ne présentent que les fiches PUBLIÉES : une fiche non publiée (brouillon, proposée,
refusée) n'est jamais accessible publiquement (renvoie 404). Lecture seule.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404, render

from apps.agenda.models import Evenement
from apps.spectacles.models import Spectacle

_PUBLIE = Spectacle.StatutModeration.PUBLIE


def accueil(request):
    """Page d'accueil : à l'affiche + créations en cours."""
    publies = Spectacle.objects.filter(statut_moderation=_PUBLIE)
    contexte = {
        "a_l_affiche": publies.filter(statut_projet=Spectacle.StatutProjet.A_L_AFFICHE)[:6],
        "en_creation": publies.filter(
            statut_projet__in=[
                Spectacle.StatutProjet.EN_CREATION,
                Spectacle.StatutProjet.EN_REPETITION,
            ]
        )[:6],
    }
    return render(request, "vitrine/accueil.html", contexte)


def liste_spectacles(request):
    """Liste filtrable des spectacles publiés (par statut de projet et portage)."""
    spectacles = Spectacle.objects.filter(statut_moderation=_PUBLIE)

    statut = request.GET.get("statut", "")
    portage = request.GET.get("portage", "")
    if statut in Spectacle.StatutProjet.values:
        spectacles = spectacles.filter(statut_projet=statut)
    if portage in Spectacle.TypePortage.values:
        spectacles = spectacles.filter(type_portage=portage)

    contexte = {
        "spectacles": spectacles,
        "statuts": Spectacle.StatutProjet.choices,
        "portages": Spectacle.TypePortage.choices,
        "statut_actif": statut,
        "portage_actif": portage,
    }
    return render(request, "vitrine/spectacles_liste.html", contexte)


def detail_spectacle(request, pk: int):
    """Fiche d'un spectacle publié (404 sinon), avec ses représentations publiques."""
    spectacle = get_object_or_404(Spectacle.objects.filter(statut_moderation=_PUBLIE), pk=pk)
    prochaines_dates = spectacle.representations.filter(
        statut_moderation=Evenement.StatutModeration.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
    ).order_by("date_debut")
    contexte = {"spectacle": spectacle, "prochaines_dates": prochaines_dates}
    return render(request, "vitrine/spectacle_detail.html", contexte)
