"""Vues du back-office (réservées au bureau).

Ferme la boucle de modération : les membres proposent (espace membre), le
bureau valide ou refuse ici. La logique de transition vit dans le service
partagé `apps.common.moderation` ; ces vues ne font qu'orchestrer et donner
un retour à l'utilisateur.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.agenda.models import Evenement
from apps.budget.models import Adhesion, RecuFiscal
from apps.budget.services import assurer_pdf_recu, donnees_depuis_adhesion, emettre_recu
from apps.coeur.roles import bureau_requis
from apps.common.fichiers import reponse_fichier_prive
from apps.common.moderation import (
    TransitionModerationInvalide,
    refuser,
    valider,
)
from apps.spectacles.models import Spectacle

from .forms import RecuFiscalForm

Propose = Spectacle.StatutModeration.PROPOSE  # même énum via le mixin Moderation


@bureau_requis
def file_moderation(request):
    """Liste des fiches en attente de validation (projets et événements)."""
    projets = Spectacle.objects.filter(statut_moderation=Propose).order_by("date_modification")
    evenements = (
        Evenement.objects.filter(statut_moderation=Propose)
        .select_related("cree_par")
        .order_by("date_debut")
    )
    return render(
        request,
        "backoffice/file_moderation.html",
        {
            "projets": projets,
            "evenements": evenements,
            "visibilites": Evenement.Visibilite.choices,
        },
    )


@bureau_requis
@require_POST
def moderer_projet(request, pk):
    """Valide ou refuse un projet proposé."""
    projet = get_object_or_404(Spectacle, pk=pk)
    _appliquer_decision(request, projet, libelle="Le projet")
    return redirect("backoffice:file_moderation")


@bureau_requis
@require_POST
def moderer_evenement(request, pk):
    """Valide (en fixant la visibilité) ou refuse un événement proposé."""
    evenement = get_object_or_404(Evenement, pk=pk)
    if request.POST.get("action") == "valider":
        visibilite = request.POST.get("visibilite", "")
        if visibilite not in Evenement.Visibilite.values:
            messages.error(request, "Visibilité invalide : validation annulée.")
            return redirect("backoffice:file_moderation")
        # Le bureau fixe la visibilité au moment de la validation (cf. modèle).
        evenement.visibilite = visibilite
    _appliquer_decision(request, evenement, libelle="L'événement")
    return redirect("backoffice:file_moderation")


def _appliquer_decision(request, fiche, *, libelle: str) -> None:
    """Applique « valider » ou « refuser » selon le champ POST `action`."""
    action = request.POST.get("action")
    try:
        if action == "valider":
            valider(fiche, par=request.user)
            messages.success(request, f"{libelle} « {fiche} » a été publié.")
        elif action == "refuser":
            refuser(fiche, par=request.user, motif=request.POST.get("motif", ""))
            messages.success(request, f"{libelle} « {fiche} » a été refusé.")
        else:
            messages.error(request, "Action inconnue.")
    except TransitionModerationInvalide as exc:
        messages.error(request, str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))


# --- Reçus fiscaux ----------------------------------------------------------


@bureau_requis
def liste_recus(request):
    """Reçus émis + adhésions éligibles à un reçu (raccourci de pré-remplissage)."""
    recus = RecuFiscal.objects.select_related("membre").all()
    adhesions_eligibles = (
        Adhesion.objects.filter(
            statut__in=[Adhesion.Statut.PAYEE, Adhesion.Statut.EXONEREE],
            montant_verse__gt=0,
        )
        .select_related("membre", "saison")
        .order_by("-saison__date_debut", "membre")
    )
    return render(
        request,
        "backoffice/recus_liste.html",
        {"recus": recus, "adhesions": adhesions_eligibles},
    )


@bureau_requis
def creer_recu(request):
    """Émet un reçu fiscal, éventuellement pré-rempli depuis une adhésion.

    Une seule voie pour les deux cas (saisie manuelle et depuis un
    enregistrement) : le formulaire est simplement pré-rempli quand une
    adhésion source est fournie (`?adhesion=<pk>`)."""
    adhesion_pk = request.POST.get("adhesion") or request.GET.get("adhesion")
    adhesion = get_object_or_404(Adhesion, pk=adhesion_pk) if adhesion_pk else None

    if request.method == "POST":
        form = RecuFiscalForm(request.POST)
        if form.is_valid():
            recu = emettre_recu(
                **form.cleaned_data,
                membre=adhesion.membre if adhesion else None,
                adhesion=adhesion,
                emis_par=request.user,
            )
            messages.success(request, f"Reçu fiscal {recu.numero} émis.")
            return redirect("backoffice:liste_recus")
    else:
        initial = donnees_depuis_adhesion(adhesion) if adhesion else None
        form = RecuFiscalForm(initial=initial)

    return render(request, "backoffice/recu_form.html", {"form": form, "adhesion": adhesion})


@bureau_requis
def telecharger_recu(request, pk):
    """Téléchargement d'un reçu pour le bureau (rend le PDF au besoin)."""
    recu = get_object_or_404(RecuFiscal, pk=pk)
    return servir_recu(recu)


def servir_recu(recu: RecuFiscal):
    """Garantit le PDF (rendu paresseux + cache) puis le sert depuis le privé.

    Réutilisé par l'espace membre pour le téléchargement par le membre concerné.
    """
    assurer_pdf_recu(recu)
    nom = f"recu-{recu.numero}{PurePosixPath(recu.fichier.name).suffix}"
    return reponse_fichier_prive(recu.fichier, nom_telechargement=nom)
