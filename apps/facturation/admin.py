"""Admin du domaine « Facturation »."""

from __future__ import annotations

from django.contrib import admin

from .models import Client, CompteurFacture, Devis, Facture, LigneDevis, LigneFacture
from .services import FactureDejaValidee, valider_facture


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


@admin.action(description="Valider et numéroter les factures sélectionnées")
def valider_factures(modeladmin, request, queryset):
    """Attribue un numéro (séquentiel, à la validation) aux factures en brouillon."""
    valides = 0
    ignorees = 0
    for facture in queryset:
        try:
            valider_facture(facture)
            valides += 1
        except FactureDejaValidee:
            ignorees += 1
    message = f"{valides} facture(s) validée(s)."
    if ignorees:
        message += f" {ignorees} ignorée(s) (déjà validée(s))."
    modeladmin.message_user(request, message)


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ("__str__", "client", "date", "statut", "total_ttc")
    list_filter = ("statut",)
    search_fields = ("numero", "objet", "client__nom")
    autocomplete_fields = ("client", "devis_origine")
    date_hierarchy = "date"
    # Numéro, dates et PDF figés par la validation (service) : non éditables à la main.
    readonly_fields = (
        "numero",
        "date",
        "date_validation",
        "fichier",
        "date_creation",
        "date_modification",
    )
    inlines = (LigneFactureInline,)
    actions = (valider_factures,)


@admin.register(CompteurFacture)
class CompteurFactureAdmin(admin.ModelAdmin):
    list_display = ("annee", "dernier")
    readonly_fields = ("annee", "dernier")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
