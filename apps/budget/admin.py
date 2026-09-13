"""Admin du domaine « Budget »."""

from __future__ import annotations

from django.contrib import admin

from .models import Adhesion, Categorie, RecuFiscal, Saison, SoldeTresorerie, Transaction


@admin.register(Saison)
class SaisonAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_debut", "date_fin")
    search_fields = ("nom",)


@admin.register(SoldeTresorerie)
class SoldeTresorerieAdmin(admin.ModelAdmin):
    list_display = ("montant", "date_pointage", "note")


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

    def has_delete_permission(self, request, obj=None) -> bool:
        """Même règle que l'écran du bureau : une adhésion dont un reçu a été
        émis ne se supprime pas — la pièce survivrait sans dire quelle
        cotisation elle couvre, et `RecuFiscalAdmin` ci-dessous refuse déjà
        qu'on touche à ses rattachements. Vaut aussi pour l'action groupée
        « Supprimer », contrôlée objet par objet."""
        if obj is not None and obj.recus_fiscaux.exists():
            return False
        return super().has_delete_permission(request, obj)


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
    """Consultation des reçus, et rien d'autre.

    L'émission passe par le service (numéro légal + snapshot) : pas de création
    directe ici. Un reçu émis ne se retouche plus et ne se supprime pas — pas
    même ses rattachements comptables, qui changent ce que le registre raconte.
    Une erreur se corrige par une pièce, pas par une réécriture."""

    list_display = ("numero", "donateur_nom", "type_versement", "montant", "date_emission")
    list_filter = ("type_versement", "forme", "date_emission")
    search_fields = ("numero", "donateur_nom")
    date_hierarchy = "date_emission"
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

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        # `instantane` est écarté de l'affichage : archive technique, illisible
        # en bloc, et le Cerfa en est déjà la forme lisible.
        return tuple(
            champ.name
            for champ in RecuFiscal._meta.fields
            if champ.name not in {"id", "instantane"}
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
