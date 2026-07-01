"""Rendu PDF (WeasyPrint), isolé et importé paresseusement.

WeasyPrint tire des dépendances natives (Pango, Cairo…) lourdes à installer sur
Windows mais triviales sur le VPS Linux. On l'importe donc UNIQUEMENT au moment
du rendu : la création des documents (numéro, snapshot) ne dépend pas de sa
présence, et les tests injectent un faux moteur en remplaçant `html_vers_pdf`.
"""

from __future__ import annotations


def html_vers_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Convertit un fragment HTML en PDF (octets).

    `base_url` permet de résoudre les ressources relatives (CSS, images).
    Lève `ModuleNotFoundError` explicite si WeasyPrint n'est pas installé.
    """
    try:
        from weasyprint import HTML  # import paresseux (dépendance native)
    except ModuleNotFoundError as exc:  # pragma: no cover - dépend de l'environnement
        raise ModuleNotFoundError(
            "WeasyPrint est requis pour générer les PDF. "
            "Installez-le (et ses libs natives) sur le serveur : voir requirements.txt."
        ) from exc

    return HTML(string=html, base_url=base_url).write_pdf()
