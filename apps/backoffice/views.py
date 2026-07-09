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
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
from apps.coeur import services as coeur_services
from apps.coeur.models import Membre, ParametresAssociation, Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU, bureau_requis
from apps.common.fichiers import reponse_fichier_prive
from apps.common.moderation import (
    TransitionModerationInvalide,
    refuser,
    valider,
)
from apps.documents.models import Document, Dossier
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
    AdhesionForm,
    CategorieForm,
    ClientForm,
    DevisForm,
    FactureForm,
    LigneDevisFormSet,
    LigneFactureFormSet,
    MembreForm,
    MembreRapideForm,
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


def appliquer_tri(request, queryset, tris, defaut_order):
    """Trie `queryset` selon `?tri=<clé>` (préfixe « - » = décroissant).

    `tris` est une **whitelist** {clé: [champs ORM]} (jamais de champ arbitraire
    depuis l'URL). Une clé absente/inconnue applique `defaut_order`. Renvoie
    `(queryset trié, tri_courant)`, où `tri_courant` est la clé signée active
    (« nom » / « -nom ») ou "" si tri par défaut — pour l'affichage des en-têtes."""
    demande = request.GET.get("tri", "")
    cle = demande.lstrip("-")
    if cle in tris:
        sens = "-" if demande.startswith("-") else ""
        return queryset.order_by(*[f"{sens}{champ}" for champ in tris[cle]]), demande
    return queryset.order_by(*defaut_order), ""


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


# --- Membres (création de comptes par le bureau) ---------------------------


_TRIS_MEMBRES = {"nom": ["nom", "prenom"], "email": ["email"]}


@bureau_requis
def liste_membres(request):
    """Liste des personnes (membres/adhérents) + accès à la création.

    Inclut les personnes sans compte de connexion (adhérents seuls). Triable
    par nom ou e-mail (clic sur l'en-tête, `?tri=`)."""
    membres = Membre.objects.select_related("user")
    membres, tri = appliquer_tri(request, membres, _TRIS_MEMBRES, ["nom", "prenom"])
    page = paginer(request, membres)
    return render(
        request,
        "backoffice/membres_liste.html",
        {"membres": page, "page": page, "tri_courant": tri},
    )


@bureau_requis
@require_POST
def basculer_visibilite_membre(request, pk):
    """Publie/dépublie un membre sur le site public (bascule `visible_sur_site`).

    C'est le bureau qui décide de l'affichage public : le membre ne peut pas se
    publier lui-même (le champ n'est pas exposé dans « Mon profil »)."""
    membre = get_object_or_404(Membre, pk=pk)
    membre.visible_sur_site = not membre.visible_sur_site
    membre.save(update_fields=["visible_sur_site", "date_modification"])
    etat = "visible sur le site" if membre.visible_sur_site else "masqué du site"
    messages.success(request, f"{membre} est désormais {etat}.")
    return redirect("backoffice:liste_membres")


@bureau_requis
@require_POST
def basculer_mise_en_avant_membre(request, pk):
    """Met/retire un membre « à la une » (vedette accordéon de la page asso)."""
    membre = get_object_or_404(Membre, pk=pk)
    membre.mis_en_avant = not membre.mis_en_avant
    membre.save(update_fields=["mis_en_avant", "date_modification"])
    etat = "à la une" if membre.mis_en_avant else "retiré de la une"
    messages.success(request, f"{membre} est désormais {etat}.")
    return redirect("backoffice:liste_membres")


def _lien_activation(request, uidb64, token):
    """URL absolue du lien d'activation (le membre y choisit son mot de passe)."""
    return request.build_absolute_uri(reverse("espace_membre:activer_compte", args=[uidb64, token]))


@bureau_requis
def creer_membre(request):
    """Crée la fiche d'une personne (adhérent/membre).

    L'accès en ligne est optionnel : si le bureau coche « ouvrir un accès », un
    compte est créé et un lien d'activation est produit (la personne y choisit
    son mot de passe — le bureau ne manipule aucun mot de passe)."""
    lien_activation = None
    if request.method == "POST":
        form = MembreForm(request.POST)
        if form.is_valid():
            membre = coeur_services.creer_membre(
                prenom=form.cleaned_data["prenom"],
                nom=form.cleaned_data["nom"],
                email=form.cleaned_data["email"],
                role_public=form.cleaned_data["role_public"],
                telephone=form.cleaned_data["telephone"],
            )
            if form.cleaned_data.get("ouvrir_acces"):
                try:
                    uidb64, token = coeur_services.ouvrir_compte(membre)
                except coeur_services.OuvertureCompteImpossible as exc:
                    messages.error(request, str(exc))
                else:
                    lien_activation = _lien_activation(request, uidb64, token)
            messages.success(request, f"Fiche créée pour {membre}.")
            form = MembreForm()  # formulaire vierge pour un éventuel suivant
    else:
        form = MembreForm()

    return render(
        request,
        "backoffice/membre_form.html",
        {"form": form, "lien_activation": lien_activation},
    )


@bureau_requis
def editer_membre(request, pk):
    """Édite l'identité d'une personne. Si elle a un compte, l'identité est
    recopiée vers le compte (l'identifiant de connexion reste inchangé)."""
    membre = get_object_or_404(Membre, pk=pk)
    form = MembreForm(request.POST or None, instance=membre, edition=True)
    if request.method == "POST" and form.is_valid():
        form.save()
        coeur_services.synchroniser_compte(membre)
        messages.success(request, "Fiche mise à jour.")
        return redirect("backoffice:liste_membres")
    return render(request, "backoffice/membre_form.html", {"form": form, "membre": membre})


@bureau_requis
@require_POST
def ouvrir_acces_membre(request, pk):
    """Ouvre un accès en ligne pour une personne sans compte : crée le compte et
    produit le lien d'activation à lui transmettre."""
    membre = get_object_or_404(Membre, pk=pk)
    lien_activation = None
    try:
        uidb64, token = coeur_services.ouvrir_compte(membre)
    except coeur_services.OuvertureCompteImpossible as exc:
        messages.error(request, str(exc))
    else:
        lien_activation = _lien_activation(request, uidb64, token)
        messages.success(
            request,
            f"Accès ouvert pour {membre}. Transmettez-lui le lien d'activation ci-dessous.",
        )
    form = MembreForm(instance=membre, edition=True)
    return render(
        request,
        "backoffice/membre_form.html",
        {"form": form, "membre": membre, "lien_activation": lien_activation},
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
    """Registre des reçus fiscaux émis (dons + cotisations).

    L'émission depuis une adhésion se fait désormais depuis l'écran Adhésions
    (bouton « Émettre un reçu ») ; ici, on saisit un reçu manuel (don) et on
    consulte/télécharge tous les reçus."""
    recus = RecuFiscal.objects.select_related("membre").all()
    page = paginer(request, recus)
    return render(request, "backoffice/recus_liste.html", {"recus": page, "page": page})


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
            # Garde-fou légal : un versement donne lieu à un seul reçu Cerfa.
            if adhesion and adhesion.recus_fiscaux.exists():
                messages.error(
                    request,
                    f"Un reçu fiscal a déjà été émis pour l'adhésion de {adhesion.membre}.",
                )
                return redirect("backoffice:liste_recus")
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


CLIENT_NOUVEAU = "__nouveau__"  # valeur du <select> pour « créer un client »


def _client_depuis_post(post):
    """Résout le client d'un devis/facture, avec création inline optionnelle.

    Si le <select> vaut « __nouveau__ », crée le client à partir des champs
    préfixés `nouveau_client-…` et renvoie un POST pointant vers lui. À appeler
    DANS une transaction : le client créé est annulé si la suite est invalide
    (pas de client orphelin). Renvoie (post, client_form, ok)."""
    if post.get("client") != CLIENT_NOUVEAU:
        return post, ClientForm(prefix="nouveau_client"), True
    client_form = ClientForm(post, prefix="nouveau_client")
    if not client_form.is_valid():
        return post, client_form, False
    nouveau = client_form.save()
    post = post.copy()
    post["client"] = str(nouveau.pk)
    return post, client_form, True


def _renumeroter_lignes(formset):
    """Attribue `ordre` selon la position d'affichage des lignes.

    « Ordre » n'est plus une colonne saisie à la main : les lignes conservent
    simplement l'ordre dans lequel elles apparaissent (position dans le formset),
    les lignes supprimées étant exclues. À appeler après `formset.save()`."""
    ordre = 0
    for form in formset.forms:
        if form.instance.pk and form not in formset.deleted_forms:
            if form.instance.ordre != ordre:
                form.instance.ordre = ordre
                form.instance.save(update_fields=["ordre"])
            ordre += 1


def _editer_facture(request, *, facture: Facture):
    """En-tête + lignes (formset) d'une facture brouillon."""
    client_form = ClientForm(prefix="nouveau_client")
    client_nouveau = False
    if request.method == "POST":
        client_nouveau = request.POST.get("client") == CLIENT_NOUVEAU
        with transaction.atomic():
            post, client_form, client_ok = _client_depuis_post(request.POST)
            form = FactureForm(post, instance=facture)
            formset = LigneFactureFormSet(post, instance=facture, prefix="lignes")
            if client_ok and form.is_valid() and formset.is_valid():
                facture = form.save()
                formset.instance = facture
                formset.save()
                _renumeroter_lignes(formset)
                messages.success(request, "Facture enregistrée.")
                return redirect("backoffice:editer_facture", pk=facture.pk)
            transaction.set_rollback(True)  # annule un client éventuellement créé
    else:
        form = FactureForm(instance=facture)
        formset = LigneFactureFormSet(instance=facture, prefix="lignes")
    return render(
        request,
        "backoffice/facture_form.html",
        {
            "form": form,
            "formset": formset,
            "client_form": client_form,
            "client_nouveau": client_nouveau,
            "facture": facture if facture.pk else None,
        },
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
    client_form = ClientForm(prefix="nouveau_client")
    client_nouveau = False
    if request.method == "POST":
        client_nouveau = request.POST.get("client") == CLIENT_NOUVEAU
        with transaction.atomic():
            post, client_form, client_ok = _client_depuis_post(request.POST)
            form = DevisForm(post, instance=devis)
            formset = LigneDevisFormSet(post, instance=devis, prefix="lignes")
            if client_ok and form.is_valid() and formset.is_valid():
                devis = form.save()
                formset.instance = devis
                formset.save()
                _renumeroter_lignes(formset)
                numeroter_devis(devis)  # attribue un numéro s'il n'en a pas
                messages.success(request, "Devis enregistré.")
                return redirect("backoffice:editer_devis", pk=devis.pk)
            transaction.set_rollback(True)  # annule un client éventuellement créé
    else:
        form = DevisForm(instance=devis)
        formset = LigneDevisFormSet(instance=devis, prefix="lignes")
    return render(
        request,
        "backoffice/devis_form.html",
        {
            "form": form,
            "formset": formset,
            "client_form": client_form,
            "client_nouveau": client_nouveau,
            "devis": devis if devis.pk else None,
        },
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


# --- Fichiers transmis au bureau -------------------------------------------
# La GED (espace association) a fusionné dans l'explorateur « Fichiers » de
# l'espace membre (branche Association, éditable par le bureau). Ne reste ici
# que la vue transverse, en lecture seule, des dossiers que les membres
# transmettent au bureau (visibilité BUREAU de leurs dossiers personnels).


@bureau_requis
def fichiers_membres(request):
    """Fichiers que des membres ont transmis au bureau (dossiers `visibilite=BUREAU`).

    Lecture seule : les dossiers privés des membres ne sont jamais exposés ici."""
    dossiers = (
        Dossier.objects.filter(visibilite=Dossier.Visibilite.BUREAU, proprietaire__isnull=False)
        .select_related("proprietaire")
        .prefetch_related(
            Prefetch(
                "documents",
                queryset=Document.objects.filter(courant=True).order_by("titre"),
            )
        )
        .order_by("proprietaire__nom", "proprietaire__prenom", "nom")
    )
    return render(request, "backoffice/fichiers_membres.html", {"dossiers": dossiers})


# --- Adhésions --------------------------------------------------------------

_TRIS_ADHESIONS = {
    "personne": ["membre__nom", "membre__prenom"],
    "saison": ["saison__date_debut", "saison__nom"],
    "statut": ["statut"],
    "attendu": ["montant_attendu"],
    "verse": ["montant_verse"],
}


@bureau_requis
def liste_adhesions(request):
    """Adhésions, filtrables par saison et par statut, triables par colonne.

    Comble le manque d'un écran dédié : jusqu'ici les adhésions ne se géraient
    que dans l'admin Django."""
    adhesions = Adhesion.objects.select_related(
        "membre", "membre__user", "saison"
    ).prefetch_related("recus_fiscaux")
    saison = _saison_demandee(request)
    if saison is not None:
        adhesions = adhesions.filter(saison=saison)
    statut = request.GET.get("statut")
    if statut in Adhesion.Statut.values:
        adhesions = adhesions.filter(statut=statut)
    else:
        statut = ""
    adhesions, tri = appliquer_tri(
        request,
        adhesions,
        _TRIS_ADHESIONS,
        ["-saison__date_debut", "membre__nom", "membre__prenom"],
    )
    page = paginer(request, adhesions)
    return render(
        request,
        "backoffice/adhesions_liste.html",
        {
            "adhesions": page,
            "page": page,
            "saisons": Saison.objects.all(),
            "saison_courante": saison,
            "statuts": Adhesion.Statut.choices,
            "statut_courant": statut,
            "tri_courant": tri,
        },
    )


def _personne_saisie(post):
    """Vrai si au moins un champ « nouvelle personne » du formulaire est renseigné."""
    return any((post.get(f"nouveau-{champ}") or "").strip() for champ in ("prenom", "nom", "email"))


def _editer_adhesion(request, *, adhesion):
    """Création/édition d'une adhésion. À la création, la personne peut être
    choisie parmi l'existant OU créée à la volée (sans compte)."""
    creation = adhesion is None
    form = AdhesionForm(request.POST or None, instance=adhesion, membre_optionnel=creation)
    form_personne = MembreRapideForm(request.POST or None, prefix="nouveau") if creation else None

    if request.method == "POST" and form.is_valid():
        membre = form.cleaned_data.get("membre")
        nouvelle_personne = creation and _personne_saisie(request.POST)
        if creation and bool(membre) == nouvelle_personne:
            # Il faut exactement une source de personne : ni les deux, ni aucune.
            form.add_error(
                "membre",
                "Choisissez une personne existante OU renseignez une nouvelle personne.",
            )
        elif nouvelle_personne and not form_personne.is_valid():
            pass  # les erreurs s'affichent sous le bloc « nouvelle personne »
        else:
            objet = form.save(commit=False)
            if nouvelle_personne:
                objet.membre = form_personne.save()
            try:
                with transaction.atomic():
                    objet.save()
            except IntegrityError:
                form.add_error(None, "Cette personne a déjà une adhésion pour cette saison.")
            else:
                messages.success(request, "Adhésion enregistrée.")
                return redirect("backoffice:liste_adhesions")

    return render(
        request,
        "backoffice/adhesion_form.html",
        {"form": form, "form_personne": form_personne, "adhesion": adhesion},
    )


@bureau_requis
def creer_adhesion(request):
    return _editer_adhesion(request, adhesion=None)


@bureau_requis
def editer_adhesion(request, pk):
    return _editer_adhesion(request, adhesion=get_object_or_404(Adhesion, pk=pk))


@bureau_requis
@require_POST
def supprimer_adhesion(request, pk):
    """Supprime une adhésion (les reçus/transactions liés sont simplement détachés)."""
    adhesion = get_object_or_404(Adhesion, pk=pk)
    adhesion.delete()
    messages.success(request, "Adhésion supprimée.")
    return redirect("backoffice:liste_adhesions")


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
