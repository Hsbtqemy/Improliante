"""Vues du front public (« vitrine »).

Ne présentent que les fiches PUBLIÉES : une fiche non publiée (brouillon, proposée,
refusée) n'est jamais accessible publiquement (renvoie 404). Lecture seule.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.agenda.models import Evenement, ImageEvenement
from apps.coeur.models import Membre
from apps.medias.models import Media
from apps.spectacles.models import ImageSpectacle, Spectacle

from .calendrier import bornes_grille, construire_calendrier
from .ical import generer_ical

_PUBLIE = Spectacle.StatutModeration.PUBLIE
_EVT_PUBLIE = Evenement.StatutModeration.PUBLIE
_EVT_PUBLIC = Evenement.Visibilite.PUBLIC


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


def _evenements_publics():
    return Evenement.objects.filter(statut_moderation=_EVT_PUBLIE, visibilite=_EVT_PUBLIC)


def agenda(request):
    """Agenda public : vue liste ou calendrier au choix (préférence mémorisée)."""
    vue = request.GET.get("vue")
    choix_explicite = vue in ("liste", "calendrier")
    if not choix_explicite:
        vue = request.COOKIES.get("agenda_vue", "liste")
        if vue not in ("liste", "calendrier"):
            vue = "liste"

    if vue == "calendrier":
        contexte = _contexte_calendrier(request)
        template = "vitrine/agenda_calendrier.html"
    else:
        contexte = {
            "evenements": _evenements_publics()
            .filter(date_debut__gte=timezone.now())
            .order_by("date_debut")
        }
        template = "vitrine/agenda_liste.html"

    reponse = render(request, template, {**contexte, "vue": vue})
    if choix_explicite:
        reponse.set_cookie("agenda_vue", vue, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return reponse


def _contexte_calendrier(request) -> dict:
    aujourdhui = timezone.localdate()
    try:
        annee = int(request.GET.get("annee", aujourdhui.year))
        mois = int(request.GET.get("mois", aujourdhui.month))
    except (TypeError, ValueError):
        annee, mois = aujourdhui.year, aujourdhui.month
    if not 1 <= mois <= 12:
        annee, mois = aujourdhui.year, aujourdhui.month

    premier, dernier = bornes_grille(annee, mois)
    evenements = _evenements_publics().filter(
        date_debut__date__gte=premier, date_debut__date__lte=dernier
    )
    premier_du_mois = date(annee, mois, 1)
    dernier_jour = calendar.monthrange(annee, mois)[1]
    return {
        "grille": construire_calendrier(annee, mois, evenements),
        "premier_du_mois": premier_du_mois,
        "mois_precedent": premier_du_mois - timedelta(days=1),
        "mois_suivant": date(annee, mois, dernier_jour) + timedelta(days=1),
        "jours_semaine": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    }


def agenda_ical(request):
    """Export iCalendar (.ics) des événements publics."""
    evenements = _evenements_publics().order_by("date_debut")
    return HttpResponse(
        generer_ical(evenements),
        content_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agenda.ics"'},
    )


def association(request):
    """Présentation de l'association et de ses membres publics."""
    membres = (
        Membre.objects.filter(visible_sur_site=True)
        .select_related("user", "photo")
        .order_by("user__last_name", "user__first_name")
    )
    return render(request, "vitrine/association.html", {"membres": membres})


def detail_membre(request, pk: int):
    """Fiche publique d'un membre (404 s'il n'est pas visible sur le site)."""
    membre = get_object_or_404(
        Membre.objects.select_related("user", "photo"), pk=pk, visible_sur_site=True
    )
    projets = (
        Spectacle.objects.filter(statut_moderation=_PUBLIE)
        .filter(Q(porteurs=membre) | Q(metteur_en_scene=membre) | Q(distribution__membre=membre))
        .distinct()
        .order_by("titre")
    )
    contexte = {"membre": membre, "projets": projets}
    return render(request, "vitrine/membre_detail.html", contexte)


def galerie(request):
    """Galerie : médias des galeries des spectacles et événements publiés."""
    return render(request, "vitrine/galerie.html", {"medias": _medias_galerie()})


def _medias_galerie():
    ids = set(
        ImageSpectacle.objects.filter(spectacle__statut_moderation=_PUBLIE).values_list(
            "media_id", flat=True
        )
    )
    ids |= set(
        ImageEvenement.objects.filter(
            evenement__statut_moderation=_EVT_PUBLIE, evenement__visibilite=_EVT_PUBLIC
        ).values_list("media_id", flat=True)
    )
    return Media.objects.filter(id__in=ids).order_by("-date_creation")
