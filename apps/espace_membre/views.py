"""Vues de l'espace membre connecté.

Règle anti-IDOR (NON NÉGOCIABLE) : chaque écran filtre selon
`request.user.membre`, jamais selon un identifiant fourni dans l'URL. Pour les
projets, la propriété se vérifie par appartenance aux `porteurs` du spectacle :
`get_object_or_404(Spectacle, pk=pk, porteurs=membre)` renvoie 404 (et non 403)
si le membre n'est pas porteur, sans révéler l'existence de la fiche.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.moderation import peut_etre_edite_par_auteur, soumettre_a_moderation
from apps.spectacles.models import Spectacle

from .forms import ProjetMembreForm


def _membre_connecte(request):
    """Fiche membre du compte connecté, ou None (ex. compte technique).

    `RelatedObjectDoesNotExist` hérite d'`AttributeError`, donc `getattr`
    renvoie proprement None si le compte n'a pas de fiche membre.
    """
    return getattr(request.user, "membre", None)


@login_required
def tableau_de_bord(request):
    """Accueil de l'espace membre : rappel de l'adhésion du membre connecté."""
    membre = _membre_connecte(request)
    adhesions = []
    if membre is not None:
        adhesions = membre.adhesions.select_related("saison").order_by("-saison__date_debut")
    return render(
        request,
        "espace_membre/tableau_de_bord.html",
        {"membre": membre, "adhesions": adhesions},
    )


@login_required
def mes_projets(request):
    """Liste des projets portés par le membre connecté (tous statuts confondus)."""
    membre = _membre_connecte(request)
    projets = []
    if membre is not None:
        # anti-IDOR : on ne liste QUE les spectacles dont le membre est porteur.
        projets = Spectacle.objects.filter(porteurs=membre).order_by("-date_modification")
    return render(
        request,
        "espace_membre/mes_projets.html",
        {"membre": membre, "projets": projets},
    )


@login_required
def creer_projet(request):
    """Création d'un projet par un membre : enregistré en brouillon, puis
    éventuellement soumis à la modération (bouton « Soumettre »)."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(
            request, "Votre compte n'est pas rattaché à une fiche membre : création impossible."
        )
        return redirect("espace_membre:tableau_de_bord")

    if request.method == "POST":
        form = ProjetMembreForm(request.POST)
        if form.is_valid():
            projet = form.save(commit=False)
            projet.cree_par = request.user
            projet.save()  # pk nécessaire avant d'ajouter le M2M porteurs
            projet.porteurs.add(membre)
            if request.POST.get("action") == "soumettre":
                soumettre_a_moderation(projet)
                messages.success(request, "Projet créé et soumis à validation du bureau.")
            else:
                messages.success(request, "Brouillon de projet enregistré.")
            return redirect("espace_membre:editer_projet", pk=projet.pk)
    else:
        form = ProjetMembreForm()

    return render(
        request,
        "espace_membre/projet_form.html",
        {"form": form, "projet": None, "editable": True},
    )


@login_required
def editer_projet(request, pk):
    """Édition d'un projet du membre. La propriété est vérifiée par le filtre
    `porteurs=membre` (anti-IDOR). L'édition n'est possible qu'en brouillon ou
    après refus ; une fiche proposée/publiée est présentée en lecture seule."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")

    projet = get_object_or_404(Spectacle, pk=pk, porteurs=membre)
    editable = peut_etre_edite_par_auteur(projet)

    if request.method == "POST":
        if not editable:
            messages.error(
                request,
                "Ce projet est en cours de validation ou publié : il n'est plus modifiable ici.",
            )
            return redirect("espace_membre:editer_projet", pk=projet.pk)
        form = ProjetMembreForm(request.POST, instance=projet)
        if form.is_valid():
            form.save()
            if request.POST.get("action") == "soumettre":
                soumettre_a_moderation(projet)
                messages.success(request, "Projet soumis à validation du bureau.")
                return redirect("espace_membre:mes_projets")
            messages.success(request, "Modifications enregistrées.")
            return redirect("espace_membre:editer_projet", pk=projet.pk)
    else:
        form = ProjetMembreForm(instance=projet)

    return render(
        request,
        "espace_membre/projet_form.html",
        {"form": form, "projet": projet, "editable": editable},
    )
