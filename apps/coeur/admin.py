"""Admin du domaine « Cœur associatif »."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LienReseau, Lieu, Membre, ParametresAssociation, Signataire, Utilisateur


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
        "user__first_name",
        "user__last_name",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("user", "photo")
    readonly_fields = ("date_creation", "date_modification")
    inlines = (LienReseauInline,)


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
