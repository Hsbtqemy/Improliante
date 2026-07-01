"""Admin du front public."""

from __future__ import annotations

from django.contrib import admin

from .models import MessageContact


@admin.register(MessageContact)
class MessageContactAdmin(admin.ModelAdmin):
    list_display = ("nom", "sujet", "email", "date_creation", "traite")
    list_filter = ("traite",)
    search_fields = ("nom", "email", "sujet", "message")
    list_editable = ("traite",)
    readonly_fields = (
        "nom",
        "email",
        "sujet",
        "message",
        "consentement",
        "date_consentement",
        "date_creation",
        "date_modification",
    )

    def has_add_permission(self, request) -> bool:
        # Les messages proviennent uniquement du formulaire public.
        return False
