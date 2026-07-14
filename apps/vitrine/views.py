"""Vues du front public (« vitrine »).

Ne présentent que les fiches PUBLIÉES : une fiche non publiée (brouillon, proposée,
refusée) n'est jamais accessible publiquement (renvoie 404). Lecture seule.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from itertools import groupby

from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.agenda.models import Evenement, ImageEvenement
from apps.coeur.models import LienReseau, Membre
from apps.coeur.services import membres_en_vedette
from apps.common.instagram import derniers_posts_instagram
from apps.medias.models import Media
from apps.spectacles.models import ImageSpectacle, Spectacle

from . import seo
from .calendrier import bornes_grille, construire_calendrier
from .forms import ContactForm
from .ical import generer_ical
from .models import MessageContact

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
        "instagram": derniers_posts_instagram(8),
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
    contexte = {
        "spectacle": spectacle,
        "prochaines_dates": prochaines_dates,
        "og_image": seo.image_partage(request, spectacle.affiche),
        "jsonld": seo.spectacle_json_ld(request, spectacle),
    }
    return render(request, "vitrine/spectacle_detail.html", contexte)


def detail_evenement(request, pk: int):
    """Fiche d'un événement public (404 sinon) — la date partageable de l'agenda."""
    evenement = get_object_or_404(
        Evenement.objects.select_related("lieu", "spectacle", "affiche"),
        pk=pk,
        statut_moderation=_EVT_PUBLIE,
        visibilite=_EVT_PUBLIC,
    )
    spectacle = evenement.spectacle if evenement.spectacle_id else None
    contexte = {
        "evenement": evenement,
        "og_image": seo.image_partage(
            request, evenement.affiche, spectacle.affiche if spectacle else None
        ),
        "jsonld": seo.evenement_json_ld(request, evenement),
    }
    return render(request, "vitrine/evenement_detail.html", contexte)


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
        contexte = {"groupes": _agenda_par_mois(request)}
        template = "vitrine/agenda_liste.html"

    reponse = render(request, template, {**contexte, "vue": vue})
    if choix_explicite:
        reponse.set_cookie("agenda_vue", vue, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return reponse


def _agenda_par_mois(request) -> list[dict]:
    """Événements publics à venir, regroupés par mois (pour la vue liste).

    Chaque événement reçoit un `jour_relatif` (« Aujourd'hui » / « Demain » / "")
    pour signaler les dates imminentes."""
    aujourdhui = timezone.localdate()
    demain = aujourdhui + timedelta(days=1)
    evenements = list(
        _evenements_publics()
        .filter(date_debut__gte=timezone.now())
        .select_related("affiche", "spectacle", "lieu")
        .order_by("date_debut")
    )
    for evenement in evenements:
        jour = timezone.localtime(evenement.date_debut).date()
        evenement.jour_relatif = (
            "Aujourd'hui" if jour == aujourdhui else "Demain" if jour == demain else ""
        )

    def cle_mois(evenement):
        local = timezone.localtime(evenement.date_debut)
        return local.year, local.month

    return [
        {"mois": date(annee, mois, 1), "evenements": list(evs)}
        for (annee, mois), evs in groupby(evenements, key=cle_mois)
    ]


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
    evenements = (
        _evenements_publics()
        .filter(date_debut__date__gte=premier, date_debut__date__lte=dernier)
        .select_related("spectacle", "affiche")
    )
    premier_du_mois = date(annee, mois, 1)
    dernier_jour = calendar.monthrange(annee, mois)[1]
    return {
        "grille": construire_calendrier(annee, mois, evenements),
        "premier_du_mois": premier_du_mois,
        "mois_precedent": premier_du_mois - timedelta(days=1),
        "mois_suivant": date(annee, mois, dernier_jour) + timedelta(days=1),
        "jours_semaine": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
        "aujourdhui": aujourdhui,
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
    """Présentation de l'association et de ses membres publics.

    Deux niveaux : une vedette (accordéon) de quelques membres — « à la une »
    puis complétée au hasard — et la grille exhaustive de tous les visibles."""
    # Projets en cours d'un membre : spectacles qu'il porte, publiés et non
    # archivés — attachés en `projets_en_cours` pour éviter les requêtes N+1.
    projets_en_cours = (
        Spectacle.objects.filter(statut_moderation=_PUBLIE)
        .exclude(statut_projet=Spectacle.StatutProjet.ARCHIVE)
        .order_by("titre")
    )
    membres = (
        Membre.objects.filter(visible_sur_site=True)
        .select_related("user", "photo")
        .prefetch_related(
            Prefetch("spectacles_portes", queryset=projets_en_cours, to_attr="projets_en_cours")
        )
        .order_by("nom", "prenom")
    )
    return render(
        request,
        "vitrine/association.html",
        {"membres": membres, "vedette": membres_en_vedette()},
    )


def handle_bluesky(url: str) -> str:
    """Extrait le handle Bluesky d'une URL de profil.

    `https://bsky.app/profile/alice.bsky.social` → `alice.bsky.social`. Tolère
    une entrée déjà réduite au handle (avec ou sans « @ »). Le handle sert de
    paramètre `actor` à l'API publique Bluesky (côté navigateur, au clic)."""
    url = (url or "").strip().rstrip("/")
    if "/profile/" in url:
        return url.rsplit("/profile/", 1)[-1]
    return url.lstrip("@")


def detail_membre(request, pk: int):
    """Fiche publique d'un membre (404 s'il n'est pas visible sur le site).

    Deux listes distinctes de spectacles publiés : ceux que le membre **porte**
    et ses **collaborations** (mise en scène ou distribution sans être porteur).
    Si le membre a un lien Bluesky, on passe son handle : la fiche propose alors
    de charger ses derniers posts (au clic, côté navigateur — cf. RGPD)."""
    membre = get_object_or_404(
        Membre.objects.select_related("user", "photo"), pk=pk, visible_sur_site=True
    )
    publies = Spectacle.objects.filter(statut_moderation=_PUBLIE)
    spectacles_portes = publies.filter(porteurs=membre).distinct().order_by("titre")
    collaborations = (
        publies.filter(distribution__membre=membre)
        .exclude(porteurs=membre)
        .distinct()
        .order_by("titre")
    )
    lien_bsky = membre.liens_reseaux.filter(reseau=LienReseau.Reseau.BLUESKY).first()
    contexte = {
        "membre": membre,
        "spectacles_portes": spectacles_portes,
        "collaborations": collaborations,
        "bluesky_handle": handle_bluesky(lien_bsky.url) if lien_bsky else "",
        "og_image": seo.image_partage(request, membre.photo),
        "jsonld": seo.membre_json_ld(request, membre),
    }
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


def contact(request):
    """Formulaire de contact : persiste le message (envoi e-mail non activé)."""
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            MessageContact.objects.create(
                nom=form.cleaned_data["nom"],
                email=form.cleaned_data["email"],
                sujet=form.cleaned_data["sujet"],
                message=form.cleaned_data["message"],
                consentement=True,
                date_consentement=timezone.now(),
            )
            # Notification e-mail au bureau : à activer plus tard (backend console).
            return redirect("vitrine:contact_merci")
    else:
        form = ContactForm()
    return render(request, "vitrine/contact.html", {"form": form})


def contact_merci(request):
    """Confirmation d'envoi du message de contact."""
    return render(request, "vitrine/contact_merci.html")


def confidentialite(request):
    """Politique de confidentialité (RGPD)."""
    return render(request, "vitrine/confidentialite.html")


def robots_txt(request):
    """robots.txt : ouvre le public, écarte les espaces privés, pointe le sitemap."""
    lignes = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /bureau/",
        "Disallow: /espace/",
        "",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lignes) + "\n", content_type="text/plain")
