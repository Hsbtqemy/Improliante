"""Admin du domaine « Budget »."""

from __future__ import annotations

from django.contrib import admin

from .models import Adhesion, Categorie, RecuFiscal, Saison, Transaction


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
    search_fields = ("membre__nom", "membre__prenom", "membre__email")
    autocomplete_fields = ("membre", "saison")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("libelle", "type_flux", "statut", "montant", "date", "categorie")
    list_filter = ("type_flux", "statut", "categorie", "saison")
    search_fields = ("libelle",)
    date_hierarchy = "date"
    autocomplete_fields = ("categorie", "saison", "facture", "adhesion")
    readonly_fields = ("date_creation", "date_modification")


@admin.register(RecuFiscal)
class RecuFiscalAdmin(admin.ModelAdmin):
    """Consultation des reçus. L'émission passe par le service (numéro légal) :
    pas de création directe en admin, et les champs figés sont en lecture seule."""

    list_display = ("numero", "donateur_nom", "type_versement", "montant", "date_emission")
    list_filter = ("type_versement", "forme", "date_emission")
    search_fields = ("numero", "donateur_nom")
    date_hierarchy = "date_emission"
    autocomplete_fields = ("membre", "adhesion", "transaction")
    readonly_fields = (
        "numero",
        "date_emission",
        "montant",
        "date_versement",
        "donateur_nom",
        "fichier",
        "emis_par",
        "date_creation",
        "date_modification",
    )

    def has_add_permission(self, request):
        return False
