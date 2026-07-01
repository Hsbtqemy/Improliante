"""Vues de l'espace membre connecté.

Règle anti-IDOR (NON NÉGOCIABLE) : chaque écran filtre selon
`request.user.membre`, jamais selon un identifiant fourni dans l'URL. Pour les
projets, la propriété se vérifie par appartenance aux `porteurs` du spectacle :
`get_object_or_404(Spectacle, pk=pk, porteurs=membre)` renvoie 404 (et non 403)
si le membre n'est pas porteur, sans révéler l'existence de la fiche.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.agenda.models import Evenement
from apps.common.fichiers import reponse_fichier_prive
from apps.common.moderation import peut_etre_edite_par_auteur, soumettre_a_moderation
from apps.documents.models import Document
from apps.spectacles.models import Spectacle

from .forms import EvenementMembreForm, ProjetMembreForm


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


# --- Événements proposés par le membre -------------------------------------
# Propriété par `cree_par` (l'événement n'a pas de « porteurs ») : le filtre
# `cree_par=request.user` est la garantie anti-IDOR.


@login_required
def mes_evenements(request):
    """Liste des événements proposés par le membre connecté."""
    evenements = Evenement.objects.filter(cree_par=request.user).order_by("-date_debut")
    return render(
        request,
        "espace_membre/mes_evenements.html",
        {"membre": _membre_connecte(request), "evenements": evenements},
    )


@login_required
def creer_evenement(request):
    """Proposition d'un événement : enregistré en brouillon puis, au choix,
    soumis à la modération. La visibilité reste fixée par le bureau."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(
            request, "Votre compte n'est pas rattaché à une fiche membre : proposition impossible."
        )
        return redirect("espace_membre:tableau_de_bord")

    if request.method == "POST":
        form = EvenementMembreForm(request.POST, membre=membre)
        if form.is_valid():
            evenement = form.save(commit=False)
            evenement.cree_par = request.user
            evenement.save()
            if request.POST.get("action") == "soumettre":
                soumettre_a_moderation(evenement)
                messages.success(request, "Événement créé et soumis à validation du bureau.")
            else:
                messages.success(request, "Brouillon d'événement enregistré.")
            return redirect("espace_membre:editer_evenement", pk=evenement.pk)
    else:
        form = EvenementMembreForm(membre=membre)

    return render(
        request,
        "espace_membre/evenement_form.html",
        {"form": form, "evenement": None, "editable": True},
    )


@login_required
def editer_evenement(request, pk):
    """Édition d'un événement du membre. Propriété vérifiée par
    `cree_par=request.user` (anti-IDOR). Verrouillé dès la proposition."""
    membre = _membre_connecte(request)
    evenement = get_object_or_404(Evenement, pk=pk, cree_par=request.user)
    editable = peut_etre_edite_par_auteur(evenement)

    if request.method == "POST":
        if not editable:
            messages.error(
                request,
                "Cet événement est en cours de validation ou publié : il n'est plus modifiable ici.",
            )
            return redirect("espace_membre:editer_evenement", pk=evenement.pk)
        form = EvenementMembreForm(request.POST, instance=evenement, membre=membre)
        if form.is_valid():
            form.save()
            if request.POST.get("action") == "soumettre":
                soumettre_a_moderation(evenement)
                messages.success(request, "Événement soumis à validation du bureau.")
                return redirect("espace_membre:mes_evenements")
            messages.success(request, "Modifications enregistrées.")
            return redirect("espace_membre:editer_evenement", pk=evenement.pk)
    else:
        form = EvenementMembreForm(instance=evenement, membre=membre)

    return render(
        request,
        "espace_membre/evenement_form.html",
        {"form": form, "evenement": evenement, "editable": editable},
    )


# --- Documents privés : consultation + téléchargement contrôlé -------------
# Les fichiers vivent hors racine web (StockagePrive) : l'accès passe TOUJOURS
# par une vue authentifiée qui contrôle la confidentialité (règle 5).


def _peut_acceder_document(user, document) -> bool:
    """Autorisation d'accès à un document selon sa confidentialité.

    - PUBLIC : tout compte connecté.
    - MEMBRES : comptes rattachés à une fiche membre.
    - PRIVÉ : bureau (staff) ou la personne qui a déposé le document.
    Le bureau (staff) a accès à tout.
    """
    if user.is_staff:
        return True
    conf = document.confidentialite
    if conf == Document.Confidentialite.PUBLIC:
        return True
    if conf == Document.Confidentialite.MEMBRES:
        return getattr(user, "membre", None) is not None
    return document.cree_par_id == user.id


def _documents_accessibles(user):
    """Documents (version courante) visibles par l'utilisateur, sans exposer
    les niveaux qu'il n'a pas le droit de voir."""
    if user.is_staff:
        return Document.objects.filter(courant=True).order_by("titre")
    niveaux = {Document.Confidentialite.PUBLIC}
    if getattr(user, "membre", None) is not None:
        niveaux.add(Document.Confidentialite.MEMBRES)
    return Document.objects.filter(courant=True, confidentialite__in=niveaux).order_by("titre")


@login_required
def mes_documents(request):
    """Liste des documents que le membre connecté a le droit de consulter."""
    documents = _documents_accessibles(request.user).select_related("dossier")
    return render(request, "espace_membre/mes_documents.html", {"documents": documents})


@login_required
def telecharger_document(request, pk):
    """Sert un document privé après contrôle des droits. Renvoie 404 (et non
    403) sur un document interdit : on ne révèle pas son existence."""
    document = get_object_or_404(Document, pk=pk)
    if not _peut_acceder_document(request.user, document):
        raise Http404
    # Nom présenté = titre + extension réelle du fichier.
    extension = PurePosixPath(document.fichier.name).suffix
    return reponse_fichier_prive(
        document.fichier, nom_telechargement=f"{document.titre}{extension}"
    )
