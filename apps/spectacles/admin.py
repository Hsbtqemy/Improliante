"""Admin du domaine « Spectacles / Projets »."""

from __future__ import annotations

from django.contrib import admin

from .models import ImageSpectacle, LigneDistribution, Spectacle


class LigneDistributionInline(admin.TabularInline):
    model = LigneDistribution
    extra = 1
    autocomplete_fields = ("membre",)


class ImageSpectacleInline(admin.TabularInline):
    model = ImageSpectacle
    extra = 1
    autocomplete_fields = ("media",)
    ordering = ("ordre",)


@admin.register(Spectacle)
class SpectacleAdmin(admin.ModelAdmin):
    list_display = ("titre", "type_portage", "statut_projet", "statut_moderation")
    list_filter = ("type_portage", "statut_projet", "statut_moderation")
    search_fields = ("titre", "synopsis")
    autocomplete_fields = (
        "porteurs",
        "affiche",
        "cree_par",
        "valide_par",
    )
    readonly_fields = ("date_creation", "date_modification")
    inlines = (LigneDistributionInline, ImageSpectacleInline)
