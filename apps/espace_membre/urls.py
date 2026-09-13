"""Routes de l'espace membre (connecté)."""

from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import MotDePasseOublieForm

app_name = "espace_membre"

urlpatterns = [
    path(
        "connexion/",
        auth_views.LoginView.as_view(template_name="espace_membre/connexion.html"),
        name="connexion",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("activation/<uidb64>/<token>/", views.activer_compte, name="activer_compte"),
    # Mot de passe oublié (FRONT-07). Les quatre vues de Django, avec les
    # gabarits du site : la demande, l'accusé, la saisie du nouveau mot de passe
    # et la confirmation. `PasswordResetConfirmView` masque le jeton dans la
    # session et redirige vers `.../set-password/` avant d'afficher le
    # formulaire — c'est elle aussi qui rend la page « lien périmé », sans
    # formulaire, quand le jeton ne vaut plus.
    path(
        "mot-de-passe/oublie/",
        auth_views.PasswordResetView.as_view(
            template_name="espace_membre/mot_de_passe_oublie.html",
            email_template_name="espace_membre/courriel/mot_de_passe_oublie.txt",
            subject_template_name="espace_membre/courriel/mot_de_passe_oublie_sujet.txt",
            form_class=MotDePasseOublieForm,
            success_url=reverse_lazy("espace_membre:mot_de_passe_oublie_envoye"),
        ),
        name="mot_de_passe_oublie",
    ),
    path(
        "mot-de-passe/envoye/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="espace_membre/mot_de_passe_oublie_envoye.html",
        ),
        name="mot_de_passe_oublie_envoye",
    ),
    path(
        "mot-de-passe/nouveau/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="espace_membre/mot_de_passe_nouveau.html",
            success_url=reverse_lazy("espace_membre:mot_de_passe_change"),
        ),
        name="mot_de_passe_nouveau",
    ),
    path(
        "mot-de-passe/change/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="espace_membre/mot_de_passe_change.html",
        ),
        name="mot_de_passe_change",
    ),
    path("espace/", views.tableau_de_bord, name="tableau_de_bord"),
    path("espace/profil/", views.mon_profil, name="mon_profil"),
    path("espace/profil/apercu/", views.apercu_ma_page, name="apercu_ma_page"),
    path(
        "espace/profil/abandonner/",
        views.abandonner_mon_brouillon,
        name="abandonner_mon_brouillon",
    ),
    path("espace/profil/image/<int:pk>/", views.image_de_brouillon, name="image_brouillon"),
    path("espace/projets/", views.mes_projets, name="mes_projets"),
    path("espace/projets/nouveau/", views.creer_projet, name="creer_projet"),
    path("espace/projets/<int:pk>/", views.voir_projet, name="voir_projet"),
    path("espace/projets/<int:pk>/modifier/", views.editer_projet, name="editer_projet"),
    path("espace/evenements/", views.mes_evenements, name="mes_evenements"),
    path("espace/evenements/nouveau/", views.creer_evenement, name="creer_evenement"),
    path("espace/evenements/<int:pk>/", views.voir_evenement, name="voir_evenement"),
    path("espace/evenements/<int:pk>/modifier/", views.editer_evenement, name="editer_evenement"),
    path(
        "espace/documents/<int:pk>/telecharger/",
        views.telecharger_document,
        name="telecharger_document",
    ),
    path("espace/fichiers/", views.mes_fichiers, name="mes_fichiers"),
    path("espace/fichiers/<int:pk>/", views.dossier_membre, name="dossier_membre"),
    path(
        "espace/fichiers/<int:pk>/editer/",
        views.editer_dossier_membre,
        name="editer_dossier_membre",
    ),
    path(
        "espace/fichiers/<int:pk>/supprimer/",
        views.supprimer_dossier_membre,
        name="supprimer_dossier_membre",
    ),
    path(
        "espace/fichiers/doc/<int:pk>/supprimer/",
        views.supprimer_document_membre,
        name="supprimer_document_membre",
    ),
    # Une seule route pour les trois espaces : c'est la vue qui décide du
    # droit selon l'espace du dossier.
    path("espace/fichiers/<int:pk>/deplacer/", views.deplacer_dossier, name="deplacer_dossier"),
    path("espace/commun/<int:pk>/", views.dossier_commun, name="dossier_commun"),
    path(
        "espace/commun/<int:pk>/editer/",
        views.editer_dossier_commun,
        name="editer_dossier_commun",
    ),
    path(
        "espace/commun/<int:pk>/supprimer/",
        views.supprimer_dossier_commun,
        name="supprimer_dossier_commun",
    ),
    path(
        "espace/commun/doc/<int:pk>/supprimer/",
        views.supprimer_document_commun,
        name="supprimer_document_commun",
    ),
    path("espace/association/<int:pk>/", views.dossier_association, name="dossier_association"),
    path(
        "espace/association/<int:pk>/editer/",
        views.editer_dossier_association,
        name="editer_dossier_association",
    ),
    path(
        "espace/association/<int:pk>/supprimer/",
        views.supprimer_dossier_association,
        name="supprimer_dossier_association",
    ),
    path(
        "espace/association/doc/<int:pk>/nouvelle-version/",
        views.nouvelle_version_association,
        name="nouvelle_version_association",
    ),
    path(
        "espace/association/doc/<int:pk>/supprimer/",
        views.supprimer_document_association,
        name="supprimer_document_association",
    ),
    path("espace/convocations/", views.mes_convocations, name="mes_convocations"),
    path("espace/convocations/<int:pk>/", views.detail_convocation, name="detail_convocation"),
    path("espace/recus/", views.mes_recus, name="mes_recus"),
    path("espace/recus/<int:pk>/telecharger/", views.telecharger_recu, name="telecharger_recu"),
]
