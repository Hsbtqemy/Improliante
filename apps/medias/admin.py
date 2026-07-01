"""Admin du domaine « Médias »."""

from __future__ import annotations

from django.contrib import admin

from .models import Media


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type_media", "date_creation", "cree_par")
    list_filter = ("type_media",)
    search_fields = ("alt", "legende")
    autocomplete_fields = ("cree_par",)
    readonly_fields = ("date_creation",)

    def save_model(self, request, obj, form, change):
        """Renseigne l'auteur (`cree_par`) à la première sauvegarde."""
        if not obj.cree_par_id:
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
