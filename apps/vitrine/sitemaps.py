"""Plan du site (sitemap.xml) — n'expose que les fiches PUBLIÉES et publiques.

Le framework `django.contrib.sitemaps` fonctionne **sans** le framework `sites` :
en l'absence de `SITE_ID`, il déduit le domaine et le schéma de la requête
(`RequestSite`). Chaque classe reflète exactement la règle de visibilité de la
vue vitrine correspondante (cf. `apps/vitrine/views.py`) : rien qui ne soit déjà
accessible publiquement n'entre dans le plan.
"""

from __future__ import annotations

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.agenda.models import Evenement
from apps.coeur.models import Membre
from apps.spectacles.models import Spectacle

_SPEC_PUBLIE = Spectacle.StatutModeration.PUBLIE
_EVT_PUBLIE = Evenement.StatutModeration.PUBLIE
_EVT_PUBLIC = Evenement.Visibilite.PUBLIC


class PagesFixesSitemap(Sitemap):
    """Pages statiques du front public (accueil, listes, contact…)."""

    changefreq = "weekly"
    priority = 0.5

    def items(self) -> list[str]:
        return [
            "vitrine:accueil",
            "vitrine:spectacles",
            "vitrine:agenda",
            "vitrine:galerie",
            "vitrine:association",
            "vitrine:contact",
        ]

    def location(self, item: str) -> str:
        return reverse(item)


class SpectaclesSitemap(Sitemap):
    """Fiches de spectacles publiées."""

    changefreq = "monthly"
    priority = 0.8

    def items(self):
        return Spectacle.objects.filter(statut_moderation=_SPEC_PUBLIE)

    def lastmod(self, obj: Spectacle):
        return obj.date_modification

    def location(self, obj: Spectacle) -> str:
        return reverse("vitrine:spectacle", args=[obj.pk])


class EvenementsSitemap(Sitemap):
    """Événements publiés et publics (une URL partageable par date)."""

    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Evenement.objects.filter(statut_moderation=_EVT_PUBLIE, visibilite=_EVT_PUBLIC)

    def lastmod(self, obj: Evenement):
        return obj.date_modification

    def location(self, obj: Evenement) -> str:
        return reverse("vitrine:evenement", args=[obj.pk])


class MembresSitemap(Sitemap):
    """Fiches de membres cochées « visible sur le site »."""

    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return Membre.objects.filter(visible_sur_site=True)

    def lastmod(self, obj: Membre):
        return obj.date_modification

    def location(self, obj: Membre) -> str:
        return reverse("vitrine:membre", args=[obj.pk])


SITEMAPS = {
    "pages": PagesFixesSitemap,
    "spectacles": SpectaclesSitemap,
    "evenements": EvenementsSitemap,
    "membres": MembresSitemap,
}
