"""Contexte de gabarit transverse pour le référencement (SEO).

Expose sur **toutes** les pages :
- `canonical` : l'URL canonique absolue de la page (sans la chaîne de requête —
  évite que `?theme=`, filtres… soient vus comme des pages distinctes) ;
- `partage_image_defaut` : l'image d'aperçu au partage par défaut, si le fichier
  `static/img/partage.jpg` existe (repli des pages sans affiche propre).
"""

from __future__ import annotations

from functools import lru_cache

from django.contrib.staticfiles import finders
from django.templatetags.static import static

IMAGE_PARTAGE = "img/partage.jpg"


@lru_cache(maxsize=1)
def _chemin_image_partage() -> str | None:
    """Chemin statique de l'image de partage si elle est présente, sinon None.

    Mémoïsé : déposer l'image après coup demande un redémarrage du serveur
    (comportement habituel des fichiers statiques)."""
    return static(IMAGE_PARTAGE) if finders.find(IMAGE_PARTAGE) else None


def seo(request):
    chemin = _chemin_image_partage()
    return {
        "canonical": request.build_absolute_uri(request.path),
        "partage_image_defaut": request.build_absolute_uri(chemin) if chemin else "",
    }
