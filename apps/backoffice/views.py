"""Vues du back-office (réservées au bureau).

Ferme la boucle de modération : les membres proposent (espace membre), le
bureau valide ou refuse ici. La logique de transition vit dans le service
partagé `apps.common.moderation` ; ces vues ne font qu'orchestrer et donner
un retour à l'utilisateur.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.contrib import messages
from django.http import Http404, HttpResponse
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
from apps.facturation.models import Client, Devis, Facture
from apps.facturation.services import (
    DevisDejaFacture,
    FactureDejaValidee,
    assurer_pdf_facture,
    numeroter_devis,
    pdf_de_devis,
    transformer_en_facture,
    valider_facture,
)
from apps.spectacles.models import Spectacle

from .forms import (
    ClientForm,
    DevisForm,
    FactureForm,
    LigneDevisFormSet,
    LigneFactureFormSet,
    RecuFiscalForm,
)

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


# --- Facturation ------------------------------------------------------------


@bureau_requis
def liste_factures(request):
    """Liste des factures (brouillons et validées)."""
    factures = Facture.objects.select_related("client").all()
    return render(request, "backoffice/factures_liste.html", {"factures": factures})


@bureau_requis
def creer_facture(request):
    """Crée une facture (brouillon) avec ses lignes."""
    return _editer_facture(request, facture=Facture())


@bureau_requis
def editer_facture(request, pk):
    """Édite une facture. Une facture validée n'est plus modifiable (document
    légal) : elle est présentée en lecture seule avec le lien de téléchargement."""
    facture = get_object_or_404(Facture, pk=pk)
    if facture.statut != Facture.Statut.BROUILLON:
        return render(request, "backoffice/facture_detail.html", {"facture": facture})
    return _editer_facture(request, facture=facture)


def _editer_facture(request, *, facture: Facture):
    """En-tête + lignes (formset) d'une facture brouillon."""
    if request.method == "POST":
        form = FactureForm(request.POST, instance=facture)
        formset = LigneFactureFormSet(request.POST, instance=facture, prefix="lignes")
        if form.is_valid() and formset.is_valid():
            facture = form.save()
            formset.instance = facture
            formset.save()
            messages.success(request, "Facture enregistrée.")
            return redirect("backoffice:editer_facture", pk=facture.pk)
    else:
        form = FactureForm(instance=facture)
        formset = LigneFactureFormSet(instance=facture, prefix="lignes")
    return render(
        request,
        "backoffice/facture_form.html",
        {"form": form, "formset": formset, "facture": facture if facture.pk else None},
    )


@bureau_requis
@require_POST
def valider_facture_vue(request, pk):
    """Valide une facture : lui attribue son numéro légal (via le service)."""
    facture = get_object_or_404(Facture, pk=pk)
    if not facture.lignes.exists():
        messages.error(request, "Impossible de valider une facture sans ligne.")
        return redirect("backoffice:editer_facture", pk=facture.pk)
    try:
        valider_facture(facture)
        messages.success(request, f"Facture {facture.numero} validée.")
    except FactureDejaValidee as exc:
        messages.error(request, str(exc))
    return redirect("backoffice:editer_facture", pk=facture.pk)


@bureau_requis
def telecharger_facture(request, pk):
    """Sert le PDF d'une facture validée (rendu paresseux + cache)."""
    facture = get_object_or_404(Facture, pk=pk)
    if facture.statut == Facture.Statut.BROUILLON:
        raise Http404  # pas de PDF légal pour un brouillon
    assurer_pdf_facture(facture)
    return reponse_fichier_prive(
        facture.fichier, nom_telechargement=f"facture-{facture.numero}.pdf"
    )


@bureau_requis
def liste_clients(request):
    """Liste des clients + création."""
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Client enregistré.")
            return redirect("backoffice:liste_clients")
    else:
        form = ClientForm()
    return render(
        request,
        "backoffice/clients.html",
        {"form": form, "clients": Client.objects.all()},
    )


# --- Devis ------------------------------------------------------------------

# Statut -> action de changement de statut autorisée depuis le back-office.
_ACTIONS_STATUT_DEVIS = {
    "envoyer": Devis.Statut.ENVOYE,
    "accepter": Devis.Statut.ACCEPTE,
    "refuser": Devis.Statut.REFUSE,
}


@bureau_requis
def liste_devis(request):
    """Liste des devis."""
    devis = Devis.objects.select_related("client").all()
    return render(request, "backoffice/devis_liste.html", {"devis": devis})


@bureau_requis
def creer_devis(request):
    """Crée un devis (brouillon) avec ses lignes ; numéro attribué à la création."""
    return _editer_devis(request, devis=Devis())


@bureau_requis
def editer_devis(request, pk):
    """Édite un devis tant qu'il n'est pas transformé en facture."""
    devis = get_object_or_404(Devis, pk=pk)
    if devis.statut == Devis.Statut.FACTURE:
        return render(request, "backoffice/devis_detail.html", {"devis": devis})
    return _editer_devis(request, devis=devis)


def _editer_devis(request, *, devis: Devis):
    if request.method == "POST":
        form = DevisForm(request.POST, instance=devis)
        formset = LigneDevisFormSet(request.POST, instance=devis, prefix="lignes")
        if form.is_valid() and formset.is_valid():
            devis = form.save()
            formset.instance = devis
            formset.save()
            numeroter_devis(devis)  # attribue un numéro s'il n'en a pas
            messages.success(request, "Devis enregistré.")
            return redirect("backoffice:editer_devis", pk=devis.pk)
    else:
        form = DevisForm(instance=devis)
        formset = LigneDevisFormSet(instance=devis, prefix="lignes")
    return render(
        request,
        "backoffice/devis_form.html",
        {"form": form, "formset": formset, "devis": devis if devis.pk else None},
    )


@bureau_requis
@require_POST
def changer_statut_devis(request, pk):
    """Fait évoluer le statut d'un devis (envoyé / accepté / refusé)."""
    devis = get_object_or_404(Devis, pk=pk)
    nouveau = _ACTIONS_STATUT_DEVIS.get(request.POST.get("action"))
    if nouveau is None or devis.statut == Devis.Statut.FACTURE:
        messages.error(request, "Changement de statut impossible.")
    else:
        devis.statut = nouveau
        devis.save(update_fields=["statut"])
        messages.success(request, f"Devis marqué « {devis.get_statut_display()} ».")
    return redirect("backoffice:editer_devis", pk=devis.pk)


@bureau_requis
@require_POST
def transformer_devis(request, pk):
    """Transforme un devis en facture brouillon (client + lignes copiés)."""
    devis = get_object_or_404(Devis, pk=pk)
    try:
        facture = transformer_en_facture(devis)
    except DevisDejaFacture as exc:
        messages.error(request, str(exc))
        return redirect("backoffice:editer_devis", pk=devis.pk)
    messages.success(request, "Devis transformé en facture (brouillon). Complétez puis validez.")
    return redirect("backoffice:editer_facture", pk=facture.pk)


@bureau_requis
def telecharger_devis(request, pk):
    """Sert le PDF d'un devis, rendu à la volée."""
    devis = get_object_or_404(Devis, pk=pk)
    reponse = HttpResponse(pdf_de_devis(devis), content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="devis-{devis.numero or devis.pk}.pdf"'
    return reponse
