"""Métadonnées de partage social (Open Graph) et données structurées (JSON-LD).

Le référencement et l'aperçu au partage réclament des URLs **absolues** : on les
fabrique depuis la requête (`request.build_absolute_uri`), sans dépendre du
framework `sites`. Derrière Nginx, le schéma (http/https) est correct grâce à
`SECURE_PROXY_SSL_HEADER` (cf. settings).

Les constructeurs renvoient une chaîne JSON déjà **échappée** pour un
`<script type="application/ld+json">` (schema.org).
"""

from __future__ import annotations

import json

from django.urls import reverse
from django.utils.html import mark_safe
from django.utils.timezone import localtime

_ASSO = "L'Improliante"

# Caractères à neutraliser dans un JSON injecté au sein d'une balise <script> :
# `<`, `>`, `&` empêchent un « </script> » malicieux ; U+2028 / U+2029 sont des
# sauts de ligne interdits dans les littéraux JavaScript.
_ECHAPPEMENTS_SCRIPT = {
    "<": "\\u003C",
    ">": "\\u003E",
    "&": "\\u0026",
    " ": "\\u2028",
    " ": "\\u2029",
}


def _media_url(request, media) -> str:
    """URL absolue du fichier d'un média image, ou "" (média absent / vidéo)."""
    fichier = getattr(media, "fichier", None)
    if media and fichier:
        return request.build_absolute_uri(fichier.url)
    return ""


def image_partage(request, *medias) -> str:
    """Première URL d'image disponible parmi `medias` (affiche, photo…), ou ""."""
    for media in medias:
        url = _media_url(request, media)
        if url:
            return url
    return ""


def json_ld(donnees) -> str:
    """Sérialise `donnees` en JSON échappé pour un contexte <script> (anti-XSS)."""
    texte = json.dumps(donnees, ensure_ascii=False)
    for brut, echappe in _ECHAPPEMENTS_SCRIPT.items():
        texte = texte.replace(brut, echappe)
    return mark_safe(texte)  # noqa: S308 — JSON contrôlé et échappé ci-dessus


def _place(evenement) -> dict | None:
    """Bloc schema.org `Place` d'un événement (fiche Lieu prioritaire, sinon texte)."""
    if evenement.lieu_id:
        lieu = evenement.lieu
        place = {"@type": "Place", "name": lieu.nom}
        if lieu.adresse or lieu.ville or lieu.code_postal:
            place["address"] = {
                "@type": "PostalAddress",
                "streetAddress": lieu.adresse,
                "postalCode": lieu.code_postal,
                "addressLocality": lieu.ville,
            }
        return place
    if evenement.lieu_texte:
        return {"@type": "Place", "name": evenement.lieu_texte}
    return None


def evenement_json_ld(request, evenement) -> str:
    """Données structurées `TheaterEvent` d'un événement public (date, lieu, œuvre)."""
    donnees = {
        "@context": "https://schema.org",
        "@type": "TheaterEvent",
        "name": evenement.titre,
        "startDate": localtime(evenement.date_debut).isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "url": request.build_absolute_uri(reverse("vitrine:evenement", args=[evenement.pk])),
        "organizer": {"@type": "Organization", "name": _ASSO},
    }
    if evenement.date_fin:
        donnees["endDate"] = localtime(evenement.date_fin).isoformat()
    if evenement.description:
        donnees["description"] = evenement.description
    spectacle = evenement.spectacle if evenement.spectacle_id else None
    image = image_partage(request, evenement.affiche, spectacle.affiche if spectacle else None)
    if image:
        donnees["image"] = [image]
    place = _place(evenement)
    if place:
        donnees["location"] = place
    if spectacle:
        donnees["workPerformed"] = {"@type": "CreativeWork", "name": spectacle.titre}
    return json_ld(donnees)


def spectacle_json_ld(request, spectacle) -> str:
    """Données structurées `CreativeWork` d'un spectacle publié (l'œuvre, hors dates)."""
    donnees = {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": spectacle.titre,
        "url": request.build_absolute_uri(reverse("vitrine:spectacle", args=[spectacle.pk])),
    }
    if spectacle.synopsis:
        donnees["description"] = spectacle.synopsis
    if spectacle.genre:
        donnees["genre"] = spectacle.genre
    image = _media_url(request, spectacle.affiche)
    if image:
        donnees["image"] = image
    return json_ld(donnees)


def membre_json_ld(request, membre) -> str:
    """Données structurées `Person` d'une fiche membre publique."""
    donnees = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": str(membre),
        "url": request.build_absolute_uri(reverse("vitrine:membre", args=[membre.pk])),
    }
    if membre.role_public:
        donnees["jobTitle"] = membre.role_public
    if membre.bio:
        donnees["description"] = membre.bio
    image = _media_url(request, membre.photo)
    if image:
        donnees["image"] = image
    liens = [lien.url for lien in membre.liens_reseaux.all()]
    if membre.site_web:
        liens.insert(0, membre.site_web)
    if liens:
        donnees["sameAs"] = liens
    return json_ld(donnees)
