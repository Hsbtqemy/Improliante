"""Rendu PDF (WeasyPrint), isolé et importé paresseusement.

WeasyPrint tire des dépendances natives (Pango, Cairo, GObject…) lourdes à
installer sur Windows mais triviales sur le VPS Linux. On l'importe donc
UNIQUEMENT au moment du rendu : la création des documents (numéro, snapshot) ne
dépend pas de sa présence, et les tests injectent un faux moteur en remplaçant
`html_vers_pdf`.
"""

from __future__ import annotations


class RenduPDFIndisponible(RuntimeError):
    """Le moteur PDF est inutilisable : WeasyPrint absent, ou ses bibliothèques
    natives (Pango/Cairo/GObject) introuvables (fréquent en dev sous Windows).

    Les vues attrapent cette exception pour afficher un message plutôt qu'un 500.
    Sur le VPS, les libs sont installées et le rendu fonctionne.
    """


def html_vers_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Convertit un fragment HTML en PDF (octets).

    `base_url` permet de résoudre les ressources relatives (CSS, images). Lève
    `RenduPDFIndisponible` si WeasyPrint n'est pas installé (`ModuleNotFoundError`)
    ou si ses bibliothèques natives ne peuvent pas être chargées (`OSError`, cas
    typique d'un poste Windows sans GTK/Pango)."""
    try:
        from weasyprint import HTML  # import paresseux (charge les libs natives)
    except ModuleNotFoundError as exc:  # pragma: no cover - dépend de l'environnement
        raise RenduPDFIndisponible(
            "WeasyPrint n'est pas installé. Installez-le et ses bibliothèques "
            "natives (Pango, Cairo…) — voir requirements.txt."
        ) from exc
    except OSError as exc:  # pragma: no cover - dépend de l'environnement
        raise RenduPDFIndisponible(
            "Les bibliothèques natives de WeasyPrint (Pango, Cairo, GObject) sont "
            "introuvables sur cette machine. La génération PDF fonctionne sur le "
            "serveur ; en local Windows, il faut installer GTK/Pango."
        ) from exc

    return HTML(string=html, base_url=base_url).write_pdf()
