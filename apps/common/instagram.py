"""Flux Instagram DE L'ASSOCIATION (compte unique) via l'API Graph de Meta.

Rendu **côté serveur** : le jeton (`settings.INSTAGRAM_TOKEN`) est un secret et
n'est jamais exposé au navigateur. Le résultat est mis en cache pour ménager les
quotas et la latence. **Dégradation silencieuse** : renvoie `[]` si non configuré
ou en cas d'erreur (réseau, jeton expiré…) — jamais d'exception qui casserait la
page.

Réglages via variables d'environnement (cf. `config/settings.py` et
`docs/instagram.md` pour l'obtention du jeton). N.B. : ce module ne concerne QUE
le compte de l'asso ; les membres gardent un simple lien Instagram.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

CLE_CACHE = "instagram_feed_asso"
# Champs demandés à l'API (Instagram Graph / Instagram Login).
CHAMPS = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp"


def derniers_posts_instagram(limite: int = 8) -> list[dict]:
    """Derniers médias du compte de l'asso (liste de dicts normalisés).

    Renvoie `[]` si aucun jeton n'est configuré ou en cas d'erreur."""
    if not settings.INSTAGRAM_TOKEN:
        return []
    en_cache = cache.get(CLE_CACHE)
    if en_cache is None:
        en_cache = _recuperer()
        cache.set(CLE_CACHE, en_cache, settings.INSTAGRAM_CACHE_TTL)
    return en_cache[:limite]


def _recuperer() -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "fields": CHAMPS,
            "limit": 24,
            "access_token": settings.INSTAGRAM_TOKEN,
        }
    )
    url = f"{settings.INSTAGRAM_API_BASE}/{settings.INSTAGRAM_USER_ID}/media?{params}"
    try:
        with urllib.request.urlopen(url, timeout=settings.INSTAGRAM_TIMEOUT) as reponse:
            data = json.loads(reponse.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — toute erreur → dégradation (pas de flux)
        return []
    return [_normaliser(item) for item in data.get("data", []) if item.get("permalink")]


def _normaliser(item: dict) -> dict:
    """Réduit un média de l'API à ce dont le gabarit a besoin.

    Pour une vidéo, `media_url` est la vidéo : on affiche `thumbnail_url`."""
    est_video = item.get("media_type") == "VIDEO"
    image = item.get("thumbnail_url") if est_video else item.get("media_url")
    return {
        "id": item.get("id", ""),
        "image": image or "",
        "permalink": item.get("permalink", ""),
        "legende": (item.get("caption") or "").strip()[:140],
        "timestamp": item.get("timestamp", ""),
    }
