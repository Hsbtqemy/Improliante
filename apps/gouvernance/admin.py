"""Admin du domaine « Gouvernance »."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import (
    ParametresGouvernance,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
    Sujet,
)
from .services import calcul_quorum, contenu_scelle, figer_les_regles, resultat_resolution


def _tous_les_champs(modele) -> list[str]:
    """Les champs d'un modèle, relations multiples comprises, sauf la clé."""
    noms = [f.name for f in modele._meta.fields if f.name != "id"]
    return noms + [f.name for f in modele._meta.many_to_many]


class _FormulaireReunionOuverte(forms.ModelForm):
    """Refuse de rattacher un enregistrement à une réunion archivée.

    L'admin écrit sans passer par les services du domaine : sans ce contrôle,
    une résolution ou un point d'ordre du jour s'ajoute encore à une séance
    close par ce chemin — c'est le constat GOU-01, relevé par l'inventaire
    ARCH-01."""

    def clean_reunion(self):
        reunion = self.cleaned_data.get("reunion")
        if reunion is not None and contenu_scelle(reunion):
            raise ValidationError(
                f"« {reunion.titre} » est archivée : son contenu est scellé. "
                "Pour la corriger, rouvrez-la d'abord (statut « Tenue »)."
            )
        return reunion


class _InlineDeReunion(admin.TabularInline):
    """Inline d'une réunion : plus rien ne s'y écrit quand la séance est close.

    `obj` est ici la réunion parente. Le sceau est le même que celui des écrans
    du bureau, lu au même endroit — une résolution, une présence ou un pouvoir
    ne s'ajoutent pas à une assemblée archivée, quel que soit le chemin."""

    def _ouverte(self, obj) -> bool:
        return obj is None or not contenu_scelle(obj)

    def has_add_permission(self, request, obj=None) -> bool:
        return self._ouverte(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._ouverte(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._ouverte(obj) and super().has_delete_permission(request, obj)


@admin.register(ParametresGouvernance)
class ParametresGouvernanceAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        # Instance unique (singleton) : pas de second enregistrement.
        return not ParametresGouvernance.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ResolutionInline(_InlineDeReunion):
    model = Resolution
    extra = 0
    autocomplete_fields = ("sujet",)
    ordering = ("ordre",)


class PresenceInline(_InlineDeReunion):
    model = Presence
    extra = 0
    autocomplete_fields = ("membre",)


class PouvoirInline(_InlineDeReunion):
    """Les pouvoirs se LISENT ici, ils ne s'y écrivent pas.

    Un pouvoir porte une règle statutaire — `max_pouvoirs_par_personne`, jamais
    codée en dur (règle 8 du dépôt) — et une conséquence : le mandant est marqué
    « représenté », donc il compte dans le quorum. Ces quatre lignes d'inline
    écrivaient en base sans l'une ni l'autre : deux pouvoirs au même mandataire
    avec un plafond à un, et aucune présence créée. La saisie d'un pouvoir
    papier se fait depuis la fiche de la réunion, qui appelle `donner_pouvoir`,
    et le retrait par `retirer_pouvoir` au même endroit.

    Le lot 4 avait annoncé « un seul service pour les pouvoirs, quel que soit le
    chemin » : c'était vrai des trois écrans du bureau, faux de cet admin."""

    model = Pouvoir
    extra = 0
    autocomplete_fields = ("mandant", "mandataire")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


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

    def get_readonly_fields(self, request, obj=None):
        """Sur une réunion archivée, seul le statut bouge encore.

        Même règle que `ReunionForm` côté back-office : le titre, la date et le
        lieu d'une séance close font partie de son dossier, mais le statut doit
        pouvoir reculer — sans quoi une clôture par erreur serait définitive."""
        figes = super().get_readonly_fields(request, obj)
        if obj is not None and contenu_scelle(obj):
            champs = [nom for nom in _tous_les_champs(Reunion) if nom != "statut"]
            return tuple(dict.fromkeys((*figes, *champs)))
        return figes

    def save_model(self, request, obj, form, change):
        """Archiver ici fige les règles, comme depuis l'écran du bureau.

        Le statut est modifiable dans cet admin : sans ce geste, une réunion
        close par ce chemin resterait soumise aux paramètres du jour, et son
        résultat changerait au prochain réglage."""
        super().save_model(request, obj, form, change)
        figer_les_regles(obj)

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
    form = _FormulaireReunionOuverte

    def get_readonly_fields(self, request, obj=None):
        """Un point passé en séance close est figé, ses notes comprises.

        Les notes d'un point partent dans le PV : les réécrire ici réécrit le
        compte rendu d'une assemblée passée, par un chemin que les écrans du
        bureau refusent."""
        figes = super().get_readonly_fields(request, obj)
        if obj is not None and obj.reunion_id and contenu_scelle(obj.reunion):
            return tuple(dict.fromkeys((*figes, *_tous_les_champs(Sujet))))
        return figes

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and obj.reunion_id and contenu_scelle(obj.reunion):
            return False
        return super().has_delete_permission(request, obj)


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
    list_select_related = ("reunion",)  # `est_adoptee` lit les règles de la réunion
    search_fields = ("intitule",)
    autocomplete_fields = ("reunion", "sujet")
    readonly_fields = ("date_creation", "date_modification")
    form = _FormulaireReunionOuverte

    def get_readonly_fields(self, request, obj=None):
        """Le décompte des voix d'une séance close ne se retouche pas.

        C'est le chemin que l'inventaire ARCH-01 nomme : cet écran ne figeait
        que les dates, donc « pour » et « contre » d'une assemblée archivée s'y
        modifiaient, et son résultat avec."""
        figes = super().get_readonly_fields(request, obj)
        if obj is not None and contenu_scelle(obj.reunion):
            return tuple(dict.fromkeys((*figes, *_tous_les_champs(Resolution))))
        return figes

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj is not None and contenu_scelle(obj.reunion):
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="Adoptée ?", boolean=True)
    def est_adoptee(self, obj):
        """Résultat du vote calculé par le service (selon les paramètres)."""
        return resultat_resolution(obj).adoptee
