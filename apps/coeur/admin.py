"""Admin du domaine « Cœur associatif »."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Lieu, Membre, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Admin de l'utilisateur custom (réutilise l'admin standard de Django)."""


@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    list_display = ("__str__", "actif", "visible_sur_site", "date_adhesion")
    list_filter = ("actif", "visible_sur_site")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("date_creation", "date_modification")


@admin.register(Lieu)
class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "code_postal")
    search_fields = ("nom", "ville")
