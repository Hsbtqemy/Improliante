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
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.agenda import services as agenda_services
from apps.agenda.models import Evenement
from apps.budget.models import RecuFiscal
from apps.budget.services import assurer_pdf_recu
from apps.coeur.roles import est_bureau
from apps.coeur.services import (
    definir_photo_membre,
    retirer_photo_membre,
    utilisateur_depuis_uidb64,
)
from apps.common.fichiers import reponse_fichier_prive
from apps.common.moderation import peut_etre_edite_par_auteur, soumettre_a_moderation
from apps.documents import services as documents_services
from apps.documents.models import Document, Dossier
from apps.documents.services import DossierNonVide
from apps.gouvernance.models import Reunion
from apps.spectacles import services as spectacles_services
from apps.spectacles.models import Spectacle

from .forms import (
    DocumentMembreForm,
    DossierCommunForm,
    EvenementMembreForm,
    LienReseauFormSet,
    ProfilMembreForm,
    ProjetMembreForm,
)


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
def mon_profil(request):
    """Édition par le membre de SA propre fiche (bio, rôle, site, réseaux, photo).

    Anti-IDOR par construction : on agit sur `request.user.membre`, jamais sur
    un identifiant d'URL — un membre ne peut éditer que sa fiche."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")

    if request.method == "POST":
        form = ProfilMembreForm(request.POST, request.FILES, instance=membre)
        formset = LienReseauFormSet(request.POST, instance=membre)
        if form.is_valid() and formset.is_valid():
            form.save()
            donnees = form.cleaned_data
            if donnees.get("photo_fichier"):
                definir_photo_membre(
                    membre, donnees["photo_fichier"], donnees["photo_alt"], cree_par=request.user
                )
            elif donnees.get("retirer_photo"):
                retirer_photo_membre(membre)
            formset.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("espace_membre:mon_profil")
    else:
        form = ProfilMembreForm(instance=membre)
        formset = LienReseauFormSet(instance=membre)

    return render(
        request,
        "espace_membre/profil_form.html",
        {"form": form, "formset": formset, "membre": membre},
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


def _appliquer_images(fiche, form, request, service):
    """Applique à la fiche (projet ou événement) les opérations d'images.

    `service` est le module du domaine (`spectacles.services` ou
    `agenda.services`) exposant `definir_affiche`, `retirer_affiche`,
    `ajouter_image_galerie` et `retirer_images_galerie`.

    Affiche : remplacée si un fichier est fourni, sinon retirée si la case est
    cochée. Galerie : ajout d'une image (si fournie) puis retrait des images
    cochées. Le retrait est borné à la fiche côté service (anti-IDOR)."""
    donnees = form.cleaned_data
    if donnees.get("affiche_fichier"):
        service.definir_affiche(
            fiche, donnees["affiche_fichier"], donnees["affiche_alt"], cree_par=request.user
        )
    elif donnees.get("retirer_affiche"):
        service.retirer_affiche(fiche)

    if donnees.get("galerie_fichier"):
        service.ajouter_image_galerie(
            fiche, donnees["galerie_fichier"], donnees["galerie_alt"], cree_par=request.user
        )

    a_retirer = [i for i in request.POST.getlist("supprimer_image") if i.isdigit()]
    if a_retirer:
        service.retirer_images_galerie(fiche, a_retirer)


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
        form = ProjetMembreForm(request.POST, request.FILES)
        if form.is_valid():
            projet = form.save(commit=False)
            projet.cree_par = request.user
            projet.save()  # pk nécessaire avant d'ajouter le M2M porteurs
            projet.porteurs.add(membre)
            _appliquer_images(projet, form, request, spectacles_services)
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
        form = ProjetMembreForm(request.POST, request.FILES, instance=projet)
        if form.is_valid():
            form.save()
            _appliquer_images(projet, form, request, spectacles_services)
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
        form = EvenementMembreForm(request.POST, request.FILES, membre=membre)
        if form.is_valid():
            evenement = form.save(commit=False)
            evenement.cree_par = request.user
            evenement.save()
            _appliquer_images(evenement, form, request, agenda_services)
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
        form = EvenementMembreForm(request.POST, request.FILES, instance=evenement, membre=membre)
        if form.is_valid():
            form.save()
            _appliquer_images(evenement, form, request, agenda_services)
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


# --- Activation de compte (lien envoyé/transmis par le bureau) --------------


def activer_compte(request, uidb64, token):
    """Le membre définit son mot de passe via un lien d'activation signé.

    Vue PUBLIQUE (le membre n'est pas encore connecté) mais protégée par un
    token à usage unique : il devient caduc dès que le mot de passe est défini,
    et expire selon `PASSWORD_RESET_TIMEOUT`. Un lien invalide n'en dit pas plus
    (pas de distinction utilisateur inconnu / token périmé)."""
    user = utilisateur_depuis_uidb64(uidb64)
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "espace_membre/activation.html", {"lien_valide": False})

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Mot de passe défini : vous pouvez maintenant vous connecter."
            )
            return redirect("espace_membre:connexion")
    else:
        form = SetPasswordForm(user)

    return render(request, "espace_membre/activation.html", {"lien_valide": True, "form": form})


# --- Documents privés : consultation + téléchargement contrôlé -------------
# Les fichiers vivent hors racine web (StockagePrive) : l'accès passe TOUJOURS
# par une vue authentifiée qui contrôle la confidentialité (règle 5).


def _peut_voir_dossier_membre(user, dossier) -> bool:
    """Autorisation de lecture d'un dossier PERSONNEL (espace PERSO).

    - branche Perso (visibilité PRIVE) : le propriétaire uniquement (bureau exclu) ;
    - branche Bureau (visibilité BUREAU) : le propriétaire et le bureau.
    (Le partage avec la troupe passe désormais par la branche « Partagé » /
    espace commun, pas par les dossiers personnels.)
    """
    membre = getattr(user, "membre", None)
    if membre is not None and dossier.proprietaire_id == membre.pk:
        return True
    if dossier.visibilite == Dossier.Visibilite.BUREAU:
        return est_bureau(user)
    return False


def _dossiers_membre_visibles(user):
    """Queryset des dossiers PERSONNELS (espace PERSO) visibles par `user` :
    ses propres dossiers, plus — pour le bureau — les dossiers « transmis au
    bureau ». Base anti-IDOR des vues de la branche personnelle."""
    membre = getattr(user, "membre", None)
    portee = Q(pk__in=())
    if membre is not None:
        portee |= Q(proprietaire=membre)
    if est_bureau(user):
        portee |= Q(visibilite=Dossier.Visibilite.BUREAU)
    return Dossier.objects.filter(espace=Dossier.Espace.PERSO).filter(portee)


def _peut_voir_espace_commun(user) -> bool:
    """Lecture de l'espace commun : tout membre (et le bureau)."""
    return getattr(user, "membre", None) is not None or est_bureau(user)


def _peut_acceder_document(user, document) -> bool:
    """Autorisation d'accès à un document, selon l'espace de son dossier.

    - Dossier PERSONNEL : suit la visibilité du dossier (`_peut_voir_dossier_membre`)
      — un dossier privé n'est PAS visible du bureau.
    - Dossier COMMUN : tout membre (troupe collaborative).
    - Dossier ASSOCIATION / non classé : logique historique par confidentialité
      (PUBLIC → tout connecté ; MEMBRES → membres ; PRIVÉ → bureau ou déposant).
    """
    dossier = document.dossier
    if dossier is not None:
        if dossier.espace == Dossier.Espace.PERSO:
            return _peut_voir_dossier_membre(user, dossier)
        if dossier.espace == Dossier.Espace.COMMUN:
            return _peut_voir_espace_commun(user)
    if est_bureau(user):
        return True
    conf = document.confidentialite
    if conf == Document.Confidentialite.PUBLIC:
        return True
    if conf == Document.Confidentialite.MEMBRES:
        return getattr(user, "membre", None) is not None
    return document.cree_par_id == user.id


def _documents_accessibles(user):
    """Documents ASSOCIATIFS (version courante) visibles par l'utilisateur.

    Les fichiers personnels et communs vivent dans leurs propres écrans et sont
    exclus ici ; les documents non classés (sans dossier) restent inclus."""
    base = Document.objects.filter(courant=True).filter(
        Q(dossier__isnull=True) | Q(dossier__espace=Dossier.Espace.ASSOCIATION)
    )
    if est_bureau(user):
        return base.order_by("titre")
    niveaux = {Document.Confidentialite.PUBLIC}
    if getattr(user, "membre", None) is not None:
        niveaux.add(Document.Confidentialite.MEMBRES)
    return base.filter(confidentialite__in=niveaux).order_by("titre")


@login_required
def mes_documents(request):
    """Liste des documents que le membre connecté a le droit de consulter."""
    documents = _documents_accessibles(request.user).select_related("dossier")
    return render(request, "espace_membre/mes_documents.html", {"documents": documents})


@login_required
def telecharger_document(request, pk):
    """Sert un document privé après contrôle des droits. Renvoie 404 (et non
    403) sur un document interdit : on ne révèle pas son existence."""
    document = get_object_or_404(Document.objects.select_related("dossier"), pk=pk)
    if not _peut_acceder_document(request.user, document):
        raise Http404
    # Nom présenté = titre + extension réelle du fichier.
    extension = PurePosixPath(document.fichier.name).suffix
    return reponse_fichier_prive(
        document.fichier, nom_telechargement=f"{document.titre}{extension}"
    )


# --- Fichiers du membre : explorateur unifié (Perso / Partagé / Bureau) ----
# Un seul explorateur, trois branches :
#   • Perso   : dossiers personnels privés (proprietaire=membre, visibilite=PRIVE) ;
#   • Partagé : espace commun collaboratif de la troupe (espace=COMMUN) ;
#   • Bureau  : dossiers transmis au bureau (proprietaire=membre, visibilite=BUREAU).
# Un sous-dossier hérite de la branche de sa racine (cf. services). Anti-accès :
# get_object_or_404 filtré par branche → un pk forgé d'une autre branche = 404.

PERSO = Dossier.Espace.PERSO
COMMUN = Dossier.Espace.COMMUN
PRIVE = Dossier.Visibilite.PRIVE
BUREAU = Dossier.Visibilite.BUREAU


def _annoter_nb_docs(queryset):
    """Ajoute `nb_docs` (nombre de documents courants) à un queryset de dossiers."""
    return queryset.annotate(nb_docs=Count("documents", filter=Q(documents__courant=True)))


def _qs_branche(membre, branche, *, racines=False):
    """Queryset des dossiers d'une branche (`perso`/`partage`/`bureau`)."""
    base = Dossier.get_root_nodes() if racines else Dossier.objects
    if branche == "partage":
        return base.filter(espace=COMMUN)
    if membre is None:
        return base.none()
    vis = BUREAU if branche == "bureau" else PRIVE
    return base.filter(espace=PERSO, proprietaire=membre, visibilite=vis)


def _arbres_fichiers(membre, dossier_courant_id=None):
    """Contexte des trois arbres (Perso / Partagé / Bureau) du panneau latéral."""

    def annote(branche):
        return Dossier.get_annotated_list_qs(_qs_branche(membre, branche).order_by("path"))

    return {
        "arbre_perso": annote("perso"),
        "arbre_partage": annote("partage"),
        "arbre_bureau": annote("bureau"),
        "dossier_courant_id": dossier_courant_id,
    }


@login_required
def mes_fichiers(request):
    """Explorateur des fichiers : trois branches Perso / Partagé / Bureau.
    POST (`branche` + nom/description) crée un dossier racine dans la branche."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")

    dossier_form = DossierCommunForm()
    branche = request.POST.get("branche")
    if request.method == "POST" and request.POST.get("form_type") == "dossier":
        dossier_form = DossierCommunForm(request.POST)
        if dossier_form.is_valid():
            nom = dossier_form.cleaned_data["nom"]
            desc = dossier_form.cleaned_data["description"]
            if branche == "partage":
                documents_services.creer_dossier_commun(nom=nom, description=desc)
            else:
                documents_services.creer_dossier_membre(
                    membre,
                    nom=nom,
                    description=desc,
                    visibilite=BUREAU if branche == "bureau" else PRIVE,
                )
            messages.success(request, "Dossier créé.")
            return redirect("espace_membre:mes_fichiers")

    contexte = {
        "perso_roots": _annoter_nb_docs(_qs_branche(membre, "perso", racines=True)),
        "partage_roots": _annoter_nb_docs(_qs_branche(membre, "partage", racines=True)),
        "bureau_roots": _annoter_nb_docs(_qs_branche(membre, "bureau", racines=True)),
        "dossier_form": dossier_form,
        "branche_active": branche,
    }
    contexte.update(_arbres_fichiers(membre))
    return render(request, "espace_membre/mes_fichiers.html", contexte)


@login_required
def dossier_membre(request, pk):
    """Détail d'un dossier personnel (branche Perso ou Bureau). Le propriétaire y
    crée des sous-dossiers / téléverse ; le bureau peut lire les dossiers
    « transmis au bureau »."""
    membre = _membre_connecte(request)
    dossier = get_object_or_404(_dossiers_membre_visibles(request.user), pk=pk)
    est_proprio = membre is not None and dossier.proprietaire_id == membre.pk

    dossier_form = DossierCommunForm()
    document_form = DocumentMembreForm()
    if request.method == "POST":
        if not est_proprio:
            raise Http404  # seul le propriétaire modifie son dossier
        if request.POST.get("form_type") == "dossier":
            dossier_form = DossierCommunForm(request.POST)
            if dossier_form.is_valid():
                documents_services.creer_dossier_membre(
                    membre,
                    nom=dossier_form.cleaned_data["nom"],
                    description=dossier_form.cleaned_data["description"],
                    parent=dossier,  # hérite de la branche du parent
                )
                messages.success(request, "Sous-dossier créé.")
                return redirect("espace_membre:dossier_membre", pk=dossier.pk)
        elif request.POST.get("form_type") == "document":
            document_form = DocumentMembreForm(request.POST, request.FILES)
            if document_form.is_valid():
                documents_services.televerser_fichier(
                    dossier,
                    titre=document_form.cleaned_data["titre"],
                    fichier=document_form.cleaned_data["fichier"],
                    description=document_form.cleaned_data["description"],
                    par=request.user,
                )
                messages.success(request, "Fichier ajouté.")
                return redirect("espace_membre:dossier_membre", pk=dossier.pk)

    visibles = _dossiers_membre_visibles(request.user)
    sous_dossiers = _annoter_nb_docs(visibles.filter(pk__in=dossier.get_children().values("pk")))
    ancetres = visibles.filter(pk__in=dossier.get_ancestors().values("pk"))
    documents = dossier.documents.filter(courant=True).select_related("cree_par").order_by("titre")
    contexte = {
        "dossier": dossier,
        "est_proprio": est_proprio,
        "branche_bureau": dossier.visibilite == BUREAU,
        "ancetres": ancetres,
        "sous_dossiers": sous_dossiers,
        "documents": documents,
        "dossier_form": dossier_form,
        "document_form": document_form,
        "url_dossier": "espace_membre:dossier_membre",
        "url_suppr_doc": "espace_membre:supprimer_document_membre",
        "url_editer": "espace_membre:editer_dossier_membre",
        "url_suppr_dossier": "espace_membre:supprimer_dossier_membre",
        "peut_ecrire": est_proprio,
    }
    contexte.update(_arbres_fichiers(membre, dossier.pk))
    return render(request, "espace_membre/dossier_detail.html", contexte)


@login_required
def editer_dossier_membre(request, pk):
    """Renomme / redécrit un dossier personnel — propriétaire seul (404 sinon)."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")
    dossier = get_object_or_404(Dossier, pk=pk, proprietaire=membre)
    if request.method == "POST":
        form = DossierCommunForm(request.POST, instance=dossier)
        if form.is_valid():
            documents_services.renommer_dossier(
                dossier,
                nom=form.cleaned_data["nom"],
                description=form.cleaned_data["description"],
            )
            messages.success(request, "Dossier mis à jour.")
            return redirect("espace_membre:dossier_membre", pk=dossier.pk)
    else:
        form = DossierCommunForm(instance=dossier)
    return render(
        request,
        "espace_membre/dossier_form.html",
        {"form": form, "dossier": dossier, "url_dossier": "espace_membre:dossier_membre"},
    )


@login_required
@require_POST
def supprimer_dossier_membre(request, pk):
    """Supprime un dossier personnel VIDE (propriétaire seul)."""
    membre = _membre_connecte(request)
    dossier = get_object_or_404(Dossier, pk=pk, proprietaire=membre)
    parent = dossier.get_parent()
    try:
        documents_services.supprimer_dossier_membre(dossier)
    except DossierNonVide:
        messages.error(request, "Le dossier doit être vide pour être supprimé.")
        return redirect("espace_membre:dossier_membre", pk=dossier.pk)
    messages.success(request, "Dossier supprimé.")
    if parent is not None:
        return redirect("espace_membre:dossier_membre", pk=parent.pk)
    return redirect("espace_membre:mes_fichiers")


@login_required
@require_POST
def supprimer_document_membre(request, pk):
    """Supprime un fichier personnel (anti-IDOR via le dossier)."""
    membre = _membre_connecte(request)
    document = get_object_or_404(Document, pk=pk, dossier__proprietaire=membre)
    dossier_id = document.dossier_id
    documents_services.supprimer_document_membre(document)
    messages.success(request, "Fichier supprimé.")
    return redirect("espace_membre:dossier_membre", pk=dossier_id)


# --- Branche « Partagé » : espace commun collaboratif ----------------------
# Tout membre y lit ET écrit. Les vues n'ouvrent que des dossiers `espace=COMMUN`.


@login_required
def dossier_commun(request, pk):
    """Détail d'un dossier commun : tout membre peut créer / téléverser."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")
    dossier = get_object_or_404(Dossier, pk=pk, espace=COMMUN)

    dossier_form = DossierCommunForm()
    document_form = DocumentMembreForm()
    if request.method == "POST":
        if request.POST.get("form_type") == "dossier":
            dossier_form = DossierCommunForm(request.POST)
            if dossier_form.is_valid():
                documents_services.creer_dossier_commun(
                    nom=dossier_form.cleaned_data["nom"],
                    description=dossier_form.cleaned_data["description"],
                    parent=dossier,
                )
                messages.success(request, "Sous-dossier créé.")
                return redirect("espace_membre:dossier_commun", pk=dossier.pk)
        elif request.POST.get("form_type") == "document":
            document_form = DocumentMembreForm(request.POST, request.FILES)
            if document_form.is_valid():
                documents_services.televerser_fichier(
                    dossier,
                    titre=document_form.cleaned_data["titre"],
                    fichier=document_form.cleaned_data["fichier"],
                    description=document_form.cleaned_data["description"],
                    par=request.user,
                )
                messages.success(request, "Fichier ajouté.")
                return redirect("espace_membre:dossier_commun", pk=dossier.pk)

    sous_dossiers = _annoter_nb_docs(dossier.get_children())
    documents = dossier.documents.filter(courant=True).select_related("cree_par").order_by("titre")
    contexte = {
        "dossier": dossier,
        "est_proprio": True,  # espace collaboratif : tout membre écrit
        "branche_bureau": False,
        "ancetres": dossier.get_ancestors(),
        "sous_dossiers": sous_dossiers,
        "documents": documents,
        "dossier_form": dossier_form,
        "document_form": document_form,
        "url_dossier": "espace_membre:dossier_commun",
        "url_suppr_doc": "espace_membre:supprimer_document_commun",
        "url_editer": "espace_membre:editer_dossier_commun",
        "url_suppr_dossier": "espace_membre:supprimer_dossier_commun",
        "peut_ecrire": True,
    }
    contexte.update(_arbres_fichiers(membre, dossier.pk))
    return render(request, "espace_membre/dossier_detail.html", contexte)


@login_required
def editer_dossier_commun(request, pk):
    """Renomme / redécrit un dossier commun (tout membre)."""
    membre = _membre_connecte(request)
    if membre is None:
        messages.error(request, "Votre compte n'est pas rattaché à une fiche membre.")
        return redirect("espace_membre:tableau_de_bord")
    dossier = get_object_or_404(Dossier, pk=pk, espace=COMMUN)
    if request.method == "POST":
        form = DossierCommunForm(request.POST, instance=dossier)
        if form.is_valid():
            documents_services.renommer_dossier(
                dossier,
                nom=form.cleaned_data["nom"],
                description=form.cleaned_data["description"],
            )
            messages.success(request, "Dossier mis à jour.")
            return redirect("espace_membre:dossier_commun", pk=dossier.pk)
    else:
        form = DossierCommunForm(instance=dossier)
    return render(
        request,
        "espace_membre/dossier_form.html",
        {"form": form, "dossier": dossier, "url_dossier": "espace_membre:dossier_commun"},
    )


@login_required
@require_POST
def supprimer_dossier_commun(request, pk):
    """Supprime un dossier commun VIDE (tout membre)."""
    if _membre_connecte(request) is None:
        raise Http404
    dossier = get_object_or_404(Dossier, pk=pk, espace=COMMUN)
    parent = dossier.get_parent()
    try:
        documents_services.supprimer_dossier_membre(dossier)
    except DossierNonVide:
        messages.error(request, "Le dossier doit être vide pour être supprimé.")
        return redirect("espace_membre:dossier_commun", pk=dossier.pk)
    messages.success(request, "Dossier supprimé.")
    if parent is not None:
        return redirect("espace_membre:dossier_commun", pk=parent.pk)
    return redirect("espace_membre:mes_fichiers")


@login_required
@require_POST
def supprimer_document_commun(request, pk):
    """Supprime un fichier de la branche partagée (tout membre)."""
    if _membre_connecte(request) is None:
        raise Http404
    document = get_object_or_404(Document, pk=pk, dossier__espace=COMMUN)
    dossier_id = document.dossier_id
    documents_services.supprimer_document_membre(document)
    messages.success(request, "Fichier supprimé.")
    return redirect("espace_membre:dossier_commun", pk=dossier_id)


# --- Convocations / comptes-rendus d'AG ------------------------------------
# Périmètre (anti-IDOR par queryset) : un membre voit les ASSEMBLÉES GÉNÉRALES
# une fois convoquées ; les réunions de bureau restent réservées au bureau
# (staff). Les réunions en préparation ne sont jamais exposées.

_STATUTS_REUNION_VISIBLES = [
    Reunion.Statut.CONVOQUEE,
    Reunion.Statut.TENUE,
    Reunion.Statut.ARCHIVEE,
]


def _reunions_visibles(user):
    """Réunions consultables par l'utilisateur, selon son rôle."""
    qs = Reunion.objects.filter(statut__in=_STATUTS_REUNION_VISIBLES)
    if est_bureau(user):
        return qs  # le bureau voit aussi les réunions de bureau
    if getattr(user, "membre", None) is None:
        return Reunion.objects.none()
    return qs.filter(
        type_reunion__in=[
            Reunion.TypeReunion.AG_ORDINAIRE,
            Reunion.TypeReunion.AG_EXTRAORDINAIRE,
        ]
    )


@login_required
def mes_convocations(request):
    """Liste des réunions (AG) auxquelles le membre connecté est convié."""
    reunions = _reunions_visibles(request.user).order_by("-date", "-id")
    return render(request, "espace_membre/mes_convocations.html", {"reunions": reunions})


@login_required
def detail_convocation(request, pk):
    """Détail d'une convocation : ordre du jour, documents joints, PV, et le
    statut personnel du membre. 404 hors périmètre de visibilité (anti-IDOR)."""
    reunion = get_object_or_404(_reunions_visibles(request.user), pk=pk)

    ordre_du_jour = reunion.sujets.order_by("ordre_du_jour", "id")

    # On ne présente que les documents que l'utilisateur a le droit d'ouvrir
    # (pas de lien mort/interdit) — le téléchargement re-contrôle les droits.
    documents = [d for d in reunion.documents.all() if _peut_acceder_document(request.user, d)]
    compte_rendu = reunion.compte_rendu
    if compte_rendu is not None and not _peut_acceder_document(request.user, compte_rendu):
        compte_rendu = None

    # Statut personnel du membre (présence figée + éventuels pouvoirs).
    membre = _membre_connecte(request)
    ma_presence = None
    pouvoir_donne = None
    pouvoir_recu = None
    if membre is not None:
        ma_presence = reunion.presences.filter(membre=membre).first()
        pouvoir_donne = reunion.pouvoirs.filter(mandant=membre).select_related("mandataire").first()
        pouvoir_recu = reunion.pouvoirs.filter(mandataire=membre).select_related("mandant").first()

    return render(
        request,
        "espace_membre/convocation_detail.html",
        {
            "reunion": reunion,
            "ordre_du_jour": ordre_du_jour,
            "documents": documents,
            "compte_rendu": compte_rendu,
            "ma_presence": ma_presence,
            "pouvoir_donne": pouvoir_donne,
            "pouvoir_recu": pouvoir_recu,
        },
    )


# --- Reçus fiscaux du membre -----------------------------------------------


@login_required
def mes_recus(request):
    """Reçus fiscaux émis au nom du membre connecté."""
    membre = _membre_connecte(request)
    recus = (
        RecuFiscal.objects.filter(membre=membre)
        if membre is not None
        else RecuFiscal.objects.none()
    )
    return render(request, "espace_membre/mes_recus.html", {"recus": recus})


@login_required
def telecharger_recu(request, pk):
    """Téléchargement d'un reçu par le membre concerné (anti-IDOR : filtre
    `membre=`). Rend le PDF au premier accès, puis sert le fichier privé."""
    membre = _membre_connecte(request)
    if membre is None:
        raise Http404
    recu = get_object_or_404(RecuFiscal, pk=pk, membre=membre)
    assurer_pdf_recu(recu)
    extension = PurePosixPath(recu.fichier.name).suffix
    return reponse_fichier_prive(recu.fichier, nom_telechargement=f"recu-{recu.numero}{extension}")
