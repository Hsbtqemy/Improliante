"""Génération d'un flux iCalendar (.ics) minimal pour l'agenda public."""

from __future__ import annotations

from datetime import UTC

from django.utils import timezone


def _echapper(texte: str) -> str:
    """Échappe les caractères spéciaux d'une valeur texte iCalendar."""
    return texte.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _horodatage_utc(valeur) -> str:
    """Formate un datetime aware en UTC iCalendar (``AAAAMMJJTHHMMSSZ``)."""
    return valeur.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def generer_ical(evenements, *, prodid: str = "-//L'Improliante//Agenda//FR") -> str:
    """Retourne un document iCalendar pour les événements donnés (déjà filtrés).

    Les lignes sont jointes par CRLF, comme l'exige la RFC 5545.
    """
    maintenant = _horodatage_utc(timezone.now())
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
        "CALSCALE:GREGORIAN",
    ]
    for evenement in evenements:
        lignes += [
            "BEGIN:VEVENT",
            f"UID:evenement-{evenement.pk}@improliante",
            f"DTSTAMP:{maintenant}",
            f"DTSTART:{_horodatage_utc(evenement.date_debut)}",
        ]
        if evenement.date_fin:
            lignes.append(f"DTEND:{_horodatage_utc(evenement.date_fin)}")
        lignes.append(f"SUMMARY:{_echapper(evenement.titre)}")
        lieu = evenement.lieu_texte or (evenement.lieu.nom if evenement.lieu_id else "")
        if lieu:
            lignes.append(f"LOCATION:{_echapper(lieu)}")
        if evenement.description:
            lignes.append(f"DESCRIPTION:{_echapper(evenement.description)}")
        lignes.append("END:VEVENT")
    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes) + "\r\n"
