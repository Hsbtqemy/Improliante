"""Admin du domaine « Budget »."""

from __future__ import annotations

from django.contrib import admin

from .models import Adhesion, Categorie, Saison, Transaction


@admin.register(Saison)
class SaisonAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_debut", "date_fin")
    search_fields = ("nom",)


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom",)
    search_fields = ("nom",)


@admin.register(Adhesion)
class AdhesionAdmin(admin.ModelAdmin):
    list_display = ("membre", "saison", "statut", "montant_attendu", "montant_verse")
    list_filter = ("statut", "saison")
    search_fields = ("membre__user__last_name", "membre__user__first_name")
    autocomplete_fields = ("membre", "saison")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("libelle", "type_flux", "statut", "montant", "date", "categorie")
    list_filter = ("type_flux", "statut", "categorie", "saison")
    search_fields = ("libelle",)
    date_hierarchy = "date"
    autocomplete_fields = ("categorie", "saison", "facture", "adhesion")
    readonly_fields = ("date_creation", "date_modification")
