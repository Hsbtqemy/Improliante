"""Admin du domaine « Facturation ».

Une pièce émise (validée, payée, annulée) est un document légal : l'admin
applique les mêmes règles que les écrans du bureau. Les transitions passent par
les services ; sur une pièce émise, seul le suivi de paiement bouge encore.
"""

from __future__ import annotations

from django.contrib import admin, messages

from .models import Client, CompteurFacture, Devis, Facture, LigneDevis, LigneFacture
from .services import ValidationRefusee, valider_facture


def _modifiable(facture) -> bool:
    """Vrai tant que la facture est un brouillon (ou n'existe pas encore)."""
    return facture is None or facture.statut == Facture.Statut.BROUILLON


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "email", "telephone")
    search_fields = ("nom", "ville", "email", "siret")


class LigneDevisInline(admin.TabularInline):
    model = LigneDevis
    extra = 1
    ordering = ("ordre",)


class LigneFactureInline(admin.TabularInline):
    """Lignes d'une facture — figées avec elle une fois émise (`obj` = la facture)."""

    model = LigneFacture
    extra = 1
    ordering = ("ordre",)

    def has_add_permission(self, request, obj=None) -> bool:
        return _modifiable(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None) -> bool:
        return _modifiable(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        return _modifiable(obj) and super().has_delete_permission(request, obj)


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
    """Attribue un numéro (séquentiel, à la validation) aux factures en brouillon.

    Mêmes refus que l'écran du bureau — déjà validée, sans ligne, avoir
    excessif : c'est le service qui les porte, pas la vue."""
    valides = 0
    for facture in queryset:
        try:
            valider_facture(facture)
            valides += 1
        except ValidationRefusee as exc:
            modeladmin.message_user(request, f"{facture} : {exc}", level=messages.WARNING)
    modeladmin.message_user(request, f"{valides} facture(s) validée(s).")


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

    def get_readonly_fields(self, request, obj=None):
        if _modifiable(obj):
            # Le statut d'un brouillon ne change qu'en validant (action) : choisi
            # dans une liste, « Validée » passerait sans numéro.
            return (*self.readonly_fields, "statut")
        # Pièce émise : tout est figé sauf le suivi de paiement — aucun écran du
        # bureau ne marque encore une facture payée, l'admin est ce chemin-là.
        # `instantane` est écarté de l'affichage : c'est une archive technique,
        # illisible en bloc, et le PDF en est déjà la forme lisible.
        return tuple(
            f.name for f in Facture._meta.fields if f.name not in {"id", "statut", "instantane"}
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not _modifiable(obj) and "statut" in form.base_fields:
            champ = form.base_fields["statut"]
            champ.choices = [c for c in champ.choices if c[0] != Facture.Statut.BROUILLON]
        return form

    def has_delete_permission(self, request, obj=None) -> bool:
        # Vaut aussi pour l'action groupée « Supprimer », contrôlée objet par objet.
        return _modifiable(obj) and super().has_delete_permission(request, obj)


@admin.register(CompteurFacture)
class CompteurFactureAdmin(admin.ModelAdmin):
    list_display = ("annee", "dernier")
    readonly_fields = ("annee", "dernier")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
