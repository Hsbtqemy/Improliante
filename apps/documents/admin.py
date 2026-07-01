"""Admin du domaine « Documents / GED »."""

from __future__ import annotations

from django.contrib import admin
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from .models import Document, Dossier


@admin.register(Dossier)
class DossierAdmin(TreeAdmin):
    form = movenodeform_factory(Dossier)
    search_fields = ("nom",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "dossier",
        "confidentialite",
        "version",
        "courant",
        "date_validite",
    )
    list_filter = ("confidentialite", "courant")
    search_fields = ("titre", "description")
    autocomplete_fields = ("dossier", "remplace", "cree_par")
    readonly_fields = ("date_creation", "date_modification")

    def save_model(self, request, obj, form, change):
        """Renseigne l'auteur (`cree_par`) à la première sauvegarde."""
        if not obj.cree_par_id:
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
