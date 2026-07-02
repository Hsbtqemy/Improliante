"""Vues du back-office (réservées au bureau).

Ferme la boucle de modération : les membres proposent (espace membre), le
bureau valide ou refuse ici. La logique de transition vit dans le service
partagé `apps.common.moderation` ; ces vues ne font qu'orchestrer et donner
un retour à l'utilisateur.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.agenda.models import Evenement
from apps.budget.models import Adhesion, Categorie, RecuFiscal, Saison, Transaction
from apps.budget.services import (
    assurer_pdf_recu,
    bilan_par_categorie,
    classeur_bilan,
    donnees_depuis_adhesion,
    emettre_recu,
    pdf_de_recu,
)
from apps.coeur.models import ParametresAssociation, Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU, bureau_requis
from apps.common.fichiers import reponse_fichier_prive
from apps.common.moderation import (
    TransitionModerationInvalide,
    refuser,
    valider,
)
from apps.documents.models import Document, Dossier
from apps.documents.services import remplacer_document
from apps.facturation.models import Client, Devis, Facture
from apps.facturation.services import (
    DevisDejaFacture,
    FactureDejaValidee,
    FactureNonAvoirable,
    assurer_pdf_facture,
    creer_avoir,
    numeroter_devis,
    pdf_de_devis,
    pdf_de_facture,
    transformer_en_facture,
    valider_facture,
)
from apps.gouvernance.models import Pouvoir, Presence, Reunion, Sujet
from apps.gouvernance.services import (
    calcul_quorum,
    mandataires_en_exces,
    preremplir_droit_de_vote,
    resultat_resolution,
)
from apps.spectacles.models import Spectacle

from .forms import (
    CategorieForm,
    ClientForm,
    DevisForm,
    DocumentForm,
    DossierForm,
    FactureForm,
    LigneDevisFormSet,
    LigneFactureFormSet,
    NouvelleVersionForm,
    ParametresAssociationForm,
    PouvoirForm,
    PresenceForm,
    RecuFiscalForm,
    ResolutionForm,
    ReunionForm,
    SaisonForm,
    SujetOrdreDuJourForm,
    TransactionForm,
)

Propose = Spectacle.StatutModeration.PROPOSE  # même énum via le mixin Moderation


def paginer(request, objets, par_page=20):
    """Retourne la page demandée (`?page=N`) d'un queryset.

    `get_page` tolère un numéro absent, non numérique ou hors bornes (renvoie
    la 1re ou la dernière page) — pas d'erreur 500 sur `?page=abc`."""
    return Paginator(objets, par_page).get_page(request.GET.get("page"))


@bureau_requis
def tableau_de_bord(request):
    """Accueil du back-office : compteurs des tâches en attente + accès rapides."""
    projets_a_moderer = Spectacle.objects.filter(statut_moderation=Propose).count()
    evenements_a_moderer = Evenement.objects.filter(statut_moderation=Propose).count()
    contexte = {
        "projets_a_moderer": projets_a_moderer,
        "evenements_a_moderer": evenements_a_moderer,
        "a_moderer": projets_a_moderer + evenements_a_moderer,
        "factures_brouillon": Facture.objects.filter(
            statut=Facture.Statut.BROUILLON, type_piece=Facture.TypePiece.FACTURE
        ).count(),
        "devis_a_suivre": Devis.objects.filter(
            statut__in=[Devis.Statut.ENVOYE, Devis.Statut.ACCEPTE]
        ).count(),
        "reunions_a_venir": Reunion.objects.filter(
            statut=Reunion.Statut.CONVOQUEE, date__gte=timezone.now()
        ).count(),
    }
    return render(request, "backoffice/tableau_de_bord.html", contexte)


# --- Paramètres & équipe ----------------------------------------------------


@bureau_requis
def parametres_association(request):
    """Édition de l'identité légale de l'association (en-tête des documents)."""
    params = ParametresAssociation.load()
    form = ParametresAssociationForm(request.POST or None, instance=params)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Paramètres de l'association enregistrés.")
        return redirect("backoffice:parametres_association")
    return render(request, "backoffice/parametres_association.html", {"form": form})


@bureau_requis
def equipe_bureau(request):
    """Gère l'appartenance au groupe « Bureau » (accès au back-office).

    Ne touche que le groupe : l'accès des comptes techniques (staff /
    superutilisateur) ne dépend pas de lui (cf. apps.coeur.roles.est_bureau)."""
    groupe, _ = Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)
    if request.method == "POST":
        user_pk = request.POST.get("utilisateur")
        user = (
            Utilisateur.objects.filter(pk=user_pk).first()
            if user_pk and user_pk.isdigit()
            else None
        )
        if user is None:
            messages.error(request, "Utilisateur introuvable.")
        elif request.POST.get("action") == "ajouter":
            user.groups.add(groupe)
            messages.success(request, f"{user} a désormais accès au bureau.")
        elif request.POST.get("action") == "retirer":
            user.groups.remove(groupe)
            messages.success(request, f"Accès bureau retiré à {user}.")
        return redirect("backoffice:equipe_bureau")

    utilisateurs = Utilisateur.objects.filter(is_active=True).order_by("username")
    membres_bureau = set(groupe.user_set.values_list("pk", flat=True))
    return render(
        request,
        "backoffice/equipe_bureau.html",
        {"utilisateurs": utilisateurs, "membres_bureau": membres_bureau},
    )


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
    page = paginer(request, recus)
    return render(
        request,
        "backoffice/recus_liste.html",
        {"recus": page, "page": page, "adhesions": adhesions_eligibles},
    )


@bureau_requis
def creer_recu(request):
    """Émet un reçu fiscal, éventuellement pré-rempli depuis une adhésion.

    Une seule voie pour les deux cas (saisie manuelle et depuis un
    enregistrement) : le formulaire est simplement pré-rempli quand une
    adhésion source est fournie (`?adhesion=<pk>`)."""
    adhesion_pk = request.POST.get("adhesion") or request.GET.get("adhesion")
    # Paramètre non numérique → aucune adhésion source (évite un 500 sur ?adhesion=abc).
    adhesion = (
        get_object_or_404(Adhesion, pk=adhesion_pk)
        if adhesion_pk and adhesion_pk.isdigit()
        else None
    )

    if request.method == "POST":
        form = RecuFiscalForm(request.POST)
        if form.is_valid():
            if request.POST.get("action") == "previsualiser":
                # Reçu transitoire (non enregistré, sans numéro) pour contrôle.
                recu = RecuFiscal(**form.cleaned_data, date_emission=timezone.localdate())
                reponse = HttpResponse(
                    pdf_de_recu(recu, apercu=True), content_type="application/pdf"
                )
                reponse["Content-Disposition"] = 'inline; filename="apercu-recu.pdf"'
                return reponse
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
    """Liste des factures (brouillons et validées), filtrable par statut."""
    factures = Facture.objects.select_related("client").all()
    statut = request.GET.get("statut")
    if statut in Facture.Statut.values:
        factures = factures.filter(statut=statut)
    page = paginer(request, factures)
    return render(
        request,
        "backoffice/factures_liste.html",
        {
            "factures": page,
            "page": page,
            "statuts": Facture.Statut.choices,
            "statut_courant": statut,
        },
    )


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
def previsualiser_facture(request, pk):
    """Aperçu PDF d'une facture (dry-run) : rendu à la volée, filigrané
    « brouillon » tant qu'elle n'est pas validée — ne consomme aucun numéro."""
    facture = get_object_or_404(Facture, pk=pk)
    apercu = facture.statut == Facture.Statut.BROUILLON
    reponse = HttpResponse(pdf_de_facture(facture, apercu=apercu), content_type="application/pdf")
    reponse["Content-Disposition"] = 'inline; filename="apercu-facture.pdf"'
    return reponse


@bureau_requis
@require_POST
def creer_avoir_vue(request, pk):
    """Crée un avoir (brouillon) sur une facture validée, à corriger puis
    valider comme une pièce à part entière (numéro de série « A… »)."""
    facture = get_object_or_404(Facture, pk=pk)
    try:
        avoir = creer_avoir(facture)
    except FactureNonAvoirable as exc:
        messages.error(request, str(exc))
        return redirect("backoffice:editer_facture", pk=facture.pk)
    messages.success(
        request, "Avoir créé (brouillon). Vérifiez les lignes, puis validez pour le numéroter."
    )
    return redirect("backoffice:editer_facture", pk=avoir.pk)


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
    page = paginer(request, devis)
    return render(request, "backoffice/devis_liste.html", {"devis": page, "page": page})


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


# --- GED (dépôt de documents côté bureau) ----------------------------------
# La consultation membre existe déjà (espace_membre) ; ici, le bureau dépose,
# classe et versionne. Le téléchargement réutilise la vue authentifiée de
# l'espace membre (le bureau a accès à tout via est_bureau).


def _traiter_formulaires_ged(request, *, parent=None):
    """Traite la création de dossier / le téléversement de document sur une page
    GED. Renvoie (dossier_form, document_form, redirection|None)."""
    dossier_form = DossierForm()
    document_form = DocumentForm()
    if request.method != "POST":
        return dossier_form, document_form, None

    if request.POST.get("form_type") == "dossier":
        dossier_form = DossierForm(request.POST)
        if dossier_form.is_valid():
            if parent is not None:
                parent.add_child(**dossier_form.cleaned_data)
            else:
                Dossier.add_root(**dossier_form.cleaned_data)
            messages.success(request, "Dossier créé.")
            return dossier_form, document_form, True
    elif request.POST.get("form_type") == "document":
        document_form = DocumentForm(request.POST, request.FILES)
        if document_form.is_valid():
            document = document_form.save(commit=False)
            document.dossier = parent
            document.cree_par = request.user
            document.save()
            messages.success(request, "Document téléversé.")
            return dossier_form, document_form, True
    return dossier_form, document_form, None


@bureau_requis
def ged_racine(request):
    """Racine de la GED : arbre des dossiers + documents non classés."""
    dossier_form, document_form, ok = _traiter_formulaires_ged(request)
    if ok:
        return redirect("backoffice:ged_racine")
    return render(
        request,
        "backoffice/ged_racine.html",
        {
            "dossiers": Dossier.objects.all(),
            "documents": Document.objects.filter(dossier__isnull=True, courant=True).order_by(
                "titre"
            ),
            "dossier_form": dossier_form,
            "document_form": document_form,
            "version_form": NouvelleVersionForm(),
        },
    )


@bureau_requis
def ged_dossier(request, pk):
    """Détail d'un dossier : sous-dossiers, documents courants, téléversement."""
    dossier = get_object_or_404(Dossier, pk=pk)
    dossier_form, document_form, ok = _traiter_formulaires_ged(request, parent=dossier)
    if ok:
        return redirect("backoffice:ged_dossier", pk=dossier.pk)
    return render(
        request,
        "backoffice/ged_dossier.html",
        {
            "dossier": dossier,
            "sous_dossiers": dossier.get_children(),
            "documents": dossier.documents.filter(courant=True).order_by("titre"),
            "dossier_form": dossier_form,
            "document_form": document_form,
            "version_form": NouvelleVersionForm(),
        },
    )


@bureau_requis
@require_POST
def ged_nouvelle_version(request, pk):
    """Remplace un document par une nouvelle version (l'ancienne est conservée)."""
    ancien = get_object_or_404(Document, pk=pk)
    form = NouvelleVersionForm(request.POST, request.FILES)
    if form.is_valid():
        remplacer_document(ancien, fichier=form.cleaned_data["fichier"], par=request.user)
        messages.success(request, "Nouvelle version enregistrée.")
    else:
        messages.error(request, "Aucun fichier fourni.")
    if ancien.dossier_id:
        return redirect("backoffice:ged_dossier", pk=ancien.dossier_id)
    return redirect("backoffice:ged_racine")


# --- Budget -----------------------------------------------------------------


def _saison_demandee(request, defaut_premiere=False):
    """Saison sélectionnée via ?saison=<pk> (ou la plus récente en repli).

    On valide que le paramètre est numérique : un `?saison=abc` ne doit pas
    provoquer d'erreur de conversion de type côté PostgreSQL (500)."""
    saison_pk = request.GET.get("saison")
    if saison_pk and saison_pk.isdigit():
        return Saison.objects.filter(pk=saison_pk).first()
    return Saison.objects.first() if defaut_premiere else None


@bureau_requis
def budget_transactions(request):
    """Liste des mouvements, filtrable par saison, type, statut et catégorie."""
    saison = _saison_demandee(request)
    transactions = Transaction.objects.select_related("categorie", "saison").order_by(
        "-date", "-id"
    )
    if saison is not None:
        transactions = transactions.filter(saison=saison)

    type_flux = request.GET.get("type_flux")
    if type_flux in Transaction.TypeFlux.values:
        transactions = transactions.filter(type_flux=type_flux)
    statut = request.GET.get("statut")
    if statut in Transaction.Statut.values:
        transactions = transactions.filter(statut=statut)
    categorie_pk = request.GET.get("categorie")
    if categorie_pk and categorie_pk.isdigit():
        transactions = transactions.filter(categorie_id=categorie_pk)

    page = paginer(request, transactions)
    return render(
        request,
        "backoffice/budget_transactions.html",
        {
            "saisons": Saison.objects.all(),
            "saison_courante": saison,
            "transactions": page,
            "page": page,
            "categories": Categorie.objects.all(),
            "types": Transaction.TypeFlux.choices,
            "statuts": Transaction.Statut.choices,
            "type_courant": type_flux,
            "statut_courant": statut,
            "categorie_courante": categorie_pk,
        },
    )


@bureau_requis
def budget_creer_transaction(request):
    return _editer_transaction(request, mouvement=None)


@bureau_requis
def budget_editer_transaction(request, pk):
    return _editer_transaction(request, mouvement=get_object_or_404(Transaction, pk=pk))


def _editer_transaction(request, *, mouvement):
    form = TransactionForm(request.POST or None, instance=mouvement)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mouvement enregistré.")
        return redirect("backoffice:budget_transactions")
    return render(
        request,
        "backoffice/transaction_form.html",
        {"form": form, "mouvement": mouvement},
    )


@bureau_requis
@require_POST
def budget_supprimer_transaction(request, pk):
    get_object_or_404(Transaction, pk=pk).delete()
    messages.success(request, "Mouvement supprimé.")
    return redirect("backoffice:budget_transactions")


@bureau_requis
def budget_bilan(request):
    """Bilan par catégorie (recettes/dépenses, prévu/réalisé) d'une saison."""
    saison = _saison_demandee(request, defaut_premiere=True)
    bilan = bilan_par_categorie(saison) if saison is not None else None
    return render(
        request,
        "backoffice/budget_bilan.html",
        {"saisons": Saison.objects.all(), "saison_courante": saison, "bilan": bilan},
    )


@bureau_requis
def budget_bilan_excel(request):
    """Exporte le bilan de la saison sélectionnée au format Excel (.xlsx)."""
    saison = _saison_demandee(request, defaut_premiere=True)
    if saison is None:
        messages.error(request, "Aucune saison à exporter.")
        return redirect("backoffice:budget_bilan")
    reponse = HttpResponse(
        classeur_bilan(saison),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    reponse["Content-Disposition"] = f'attachment; filename="bilan-{saison.pk}.xlsx"'
    return reponse


@bureau_requis
def budget_saisons(request):
    form = SaisonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saison enregistrée.")
        return redirect("backoffice:budget_saisons")
    return render(
        request,
        "backoffice/budget_saisons.html",
        {"form": form, "saisons": Saison.objects.all()},
    )


@bureau_requis
def budget_categories(request):
    form = CategorieForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie enregistrée.")
        return redirect("backoffice:budget_categories")
    return render(
        request,
        "backoffice/budget_categories.html",
        {"form": form, "categories": Categorie.objects.all()},
    )


# --- Gouvernance (réunions / AG) --------------------------------------------


@bureau_requis
def gouvernance_reunions(request):
    """Liste des réunions/AG + création."""
    form = ReunionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reunion = form.save()
        messages.success(request, "Réunion créée.")
        return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)
    return render(
        request,
        "backoffice/gouvernance_reunions.html",
        {"form": form, "reunions": Reunion.objects.all()},
    )


@bureau_requis
def gouvernance_reunion(request, pk):
    """Détail d'une réunion : quorum, ordre du jour, présences, pouvoirs,
    résolutions (avec résultat calculé)."""
    reunion = get_object_or_404(Reunion, pk=pk)
    resolutions = [(r, resultat_resolution(r)) for r in reunion.resolutions.all()]
    return render(
        request,
        "backoffice/gouvernance_reunion.html",
        {
            "reunion": reunion,
            "quorum": calcul_quorum(reunion),
            "ordre_du_jour": reunion.sujets.order_by("ordre_du_jour", "id"),
            "presences": reunion.presences.select_related("membre").order_by("membre"),
            "pouvoirs": reunion.pouvoirs.select_related("mandant", "mandataire"),
            "resolutions": resolutions,
            "mandataires_en_exces": mandataires_en_exces(reunion),
            "saisons": Saison.objects.all(),
            "sujet_form": SujetOrdreDuJourForm(),
            "presence_form": PresenceForm(),
            "pouvoir_form": PouvoirForm(),
            "resolution_form": ResolutionForm(reunion=reunion),
        },
    )


@bureau_requis
@require_POST
def gouvernance_ajouter_sujet(request, pk):
    reunion = get_object_or_404(Reunion, pk=pk)
    form = SujetOrdreDuJourForm(request.POST)
    if form.is_valid():
        sujet = form.save(commit=False)
        sujet.reunion = reunion
        sujet.statut = Sujet.Statut.ORDRE_DU_JOUR
        sujet.save()
        messages.success(request, "Sujet ajouté à l'ordre du jour.")
    else:
        messages.error(request, "Sujet invalide.")
    return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)


@bureau_requis
@require_POST
def gouvernance_saisir_presence(request, pk):
    reunion = get_object_or_404(Reunion, pk=pk)
    form = PresenceForm(request.POST)
    if form.is_valid():
        # update_or_create : ré-enregistrer un membre met à jour sa présence
        # (contrainte d'unicité reunion+membre).
        Presence.objects.update_or_create(
            reunion=reunion,
            membre=form.cleaned_data["membre"],
            defaults={
                "statut": form.cleaned_data["statut"],
                "peut_voter": form.cleaned_data["peut_voter"],
            },
        )
        messages.success(request, "Présence enregistrée.")
    else:
        messages.error(request, "Présence invalide.")
    return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)


@bureau_requis
@require_POST
def gouvernance_preremplir_votes(request, pk):
    reunion = get_object_or_404(Reunion, pk=pk)
    saison_pk = request.POST.get("saison")
    saison = (
        Saison.objects.filter(pk=saison_pk).first() if saison_pk and saison_pk.isdigit() else None
    )
    try:
        nb = preremplir_droit_de_vote(reunion, saison=saison)
        messages.success(request, f"Droits de vote mis à jour ({nb} présence(s)).")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)


@bureau_requis
@require_POST
def gouvernance_ajouter_pouvoir(request, pk):
    reunion = get_object_or_404(Reunion, pk=pk)
    form = PouvoirForm(request.POST)
    if form.is_valid():
        # update_or_create : un mandant ne donne qu'un pouvoir par réunion.
        Pouvoir.objects.update_or_create(
            reunion=reunion,
            mandant=form.cleaned_data["mandant"],
            defaults={"mandataire": form.cleaned_data["mandataire"]},
        )
        messages.success(request, "Pouvoir enregistré.")
    else:
        messages.error(request, "; ".join(form.non_field_errors()) or "Pouvoir invalide.")
    return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)


@bureau_requis
@require_POST
def gouvernance_ajouter_resolution(request, pk):
    reunion = get_object_or_404(Reunion, pk=pk)
    form = ResolutionForm(request.POST, reunion=reunion)
    if form.is_valid():
        resolution = form.save(commit=False)
        resolution.reunion = reunion
        resolution.save()
        messages.success(request, "Résolution enregistrée.")
    else:
        messages.error(request, "Résolution invalide.")
    return redirect("backoffice:gouvernance_reunion", pk=reunion.pk)
