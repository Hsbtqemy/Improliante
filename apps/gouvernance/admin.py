"""Admin du domaine « Gouvernance »."""

from __future__ import annotations

from django.contrib import admin

from .models import (
    ParametresGouvernance,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
    Sujet,
)
from .services import calcul_quorum, resultat_resolution


@admin.register(ParametresGouvernance)
class ParametresGouvernanceAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        # Instance unique (singleton) : pas de second enregistrement.
        return not ParametresGouvernance.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ResolutionInline(admin.TabularInline):
    model = Resolution
    extra = 0
    autocomplete_fields = ("sujet",)
    ordering = ("ordre",)


class PresenceInline(admin.TabularInline):
    model = Presence
    extra = 0
    autocomplete_fields = ("membre",)


class PouvoirInline(admin.TabularInline):
    model = Pouvoir
    extra = 0
    autocomplete_fields = ("mandant", "mandataire")


@admin.register(Reunion)
class ReunionAdmin(admin.ModelAdmin):
    list_display = ("titre", "type_reunion", "statut", "date")
    list_filter = ("type_reunion", "statut")
    search_fields = ("titre",)
    date_hierarchy = "date"
    autocomplete_fields = ("compte_rendu", "evenement")
    filter_horizontal = ("documents",)
    readonly_fields = ("quorum", "date_creation", "date_modification")
    inlines = (ResolutionInline, PresenceInline, PouvoirInline)

    @admin.display(description="Quorum")
    def quorum(self, obj):
        """Affiche l'état du quorum (calculé par le service)."""
        if obj.pk is None:
            return "—"
        resultat = calcul_quorum(obj)
        if not resultat.applicable:
            return "non applicable (réunion de bureau)"
        etat = "atteint" if resultat.atteint else "NON atteint"
        return (
            f"{etat} — {resultat.presents_representes}/{resultat.electorat} "
            f"(seuil {resultat.seuil})"
        )


@admin.register(Sujet)
class SujetAdmin(admin.ModelAdmin):
    list_display = ("titre", "statut", "priorite", "propose_par", "reunion")
    list_filter = ("statut", "priorite")
    search_fields = ("titre", "description")
    autocomplete_fields = ("propose_par", "reunion", "fusionne_dans")
    filter_horizontal = ("documents",)
    readonly_fields = ("date_creation", "date_modification")


@admin.register(Resolution)
class ResolutionAdmin(admin.ModelAdmin):
    list_display = (
        "intitule",
        "reunion",
        "type_majorite",
        "nombre_pour",
        "nombre_contre",
        "nombre_abstention",
        "est_adoptee",
    )
    list_filter = ("type_majorite",)
    search_fields = ("intitule",)
    autocomplete_fields = ("reunion", "sujet")
    readonly_fields = ("date_creation", "date_modification")

    @admin.display(description="Adoptée ?", boolean=True)
    def est_adoptee(self, obj):
        """Résultat du vote calculé par le service (selon les paramètres)."""
        return resultat_resolution(obj).adoptee
