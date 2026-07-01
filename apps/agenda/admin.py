"""Admin du domaine « Agenda »."""

from __future__ import annotations

from django.contrib import admin

from .models import Evenement, ImageEvenement, Intervention


class InterventionInline(admin.TabularInline):
    model = Intervention
    extra = 1
    autocomplete_fields = ("membre",)


class ImageEvenementInline(admin.TabularInline):
    model = ImageEvenement
    extra = 1
    autocomplete_fields = ("media",)
    ordering = ("ordre",)


@admin.register(Evenement)
class EvenementAdmin(admin.ModelAdmin):
    list_display = ("titre", "date_debut", "visibilite", "statut_moderation", "spectacle")
    list_filter = ("visibilite", "statut_moderation")
    search_fields = ("titre", "description")
    date_hierarchy = "date_debut"
    autocomplete_fields = ("lieu", "spectacle", "affiche", "cree_par", "valide_par")
    readonly_fields = ("date_creation", "date_modification")
    inlines = (InterventionInline, ImageEvenementInline)
