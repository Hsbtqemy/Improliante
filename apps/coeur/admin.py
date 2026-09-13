"""Admin du domaine « Cœur associatif »."""

from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import LienReseau, Lieu, Membre, ParametresAssociation, Signataire, Utilisateur
from .services import aligner_brouillon_apres_saisie, brouillon_en_attente


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Admin de l'utilisateur custom (réutilise l'admin standard de Django)."""


class LienReseauInline(admin.TabularInline):
    model = LienReseau
    extra = 1
    ordering = ("ordre",)


@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    list_display = ("__str__", "actif", "visible_sur_site", "mis_en_avant", "date_adhesion")
    list_filter = ("actif", "visible_sur_site", "mis_en_avant")
    search_fields = (
        "prenom",
        "nom",
        "slug",
        "email",
        "user__username",
    )
    autocomplete_fields = ("user", "photo")
    readonly_fields = ("date_creation", "date_modification")
    inlines = (LienReseauInline,)

    def save_model(self, request, obj, form, change):
        """Écrire une fiche, c'est publier : elle porte la version publique.

        L'admin écrivait `Membre` sans passer par l'alignement que le
        back-office fait depuis sa relecture — c'était la porte de service, et
        elle rouvrait le décalage : le brouillon de la personne gardait
        l'ancien texte, son écran d'édition annonçait pour toujours des
        modifications non publiées, et sa prochaine publication rendait la
        fiche à sa valeur d'avant.

        Le contenu d'avant est relu en base, et pas sur `obj` : le formulaire y
        a déjà posé les valeurs reçues.
        """
        avant = {}
        if change and obj.pk:
            avant = dict(Membre.objects.get(pk=obj.pk).contenu_public)
        super().save_model(request, obj, form, change)
        if not change:
            return
        aligner_brouillon_apres_saisie(obj, avant)
        if brouillon_en_attente(obj):
            messages.warning(
                request,
                f"{obj} a des modifications non publiées sur sa page : "
                "elles recouvriront cette saisie lorsqu'elle publiera.",
            )


@admin.register(Lieu)
class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "code_postal")
    search_fields = ("nom", "ville")


@admin.register(Signataire)
class SignataireAdmin(admin.ModelAdmin):
    list_display = ("nom", "qualite", "actif")
    list_filter = ("actif",)
    search_fields = ("nom", "qualite")
    autocomplete_fields = ("membre",)


@admin.register(ParametresAssociation)
class ParametresAssociationAdmin(admin.ModelAdmin):
    """Instance unique (singleton) : on édite, on ne crée ni ne supprime."""

    def has_add_permission(self, request):
        return not ParametresAssociation.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
