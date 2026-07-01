"""Admin du domaine « Facturation »."""

from __future__ import annotations

from django.contrib import admin

from .models import Client, Devis, Facture, LigneDevis, LigneFacture


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "email", "telephone")
    search_fields = ("nom", "ville", "email", "siret")


class LigneDevisInline(admin.TabularInline):
    model = LigneDevis
    extra = 1
    ordering = ("ordre",)


class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 1
    ordering = ("ordre",)


@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display = ("__str__", "client", "date", "statut", "total_ttc")
    list_filter = ("statut",)
    search_fields = ("numero", "objet", "client__nom")
    autocomplete_fields = ("client",)
    date_hierarchy = "date"
    readonly_fields = ("date_creation", "date_modification")
    inlines = (LigneDevisInline,)


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ("__str__", "client", "date", "statut", "total_ttc")
    list_filter = ("statut",)
    search_fields = ("numero", "objet", "client__nom")
    autocomplete_fields = ("client", "devis_origine")
    date_hierarchy = "date"
    readonly_fields = ("date_creation", "date_modification", "date_validation")
    inlines = (LigneFactureInline,)
