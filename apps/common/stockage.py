"""Stockage de fichiers privés (hors racine web publique).

`StockagePrive` écrit sous `settings.MEDIA_PRIVE_ROOT`, un dossier que Nginx
n'expose PAS directement. Les fichiers qui y résident ne sont accessibles que
via une vue authentifiée contrôlant les droits (cf. `apps.common.fichiers`).

La classe est passée telle quelle comme `storage=` d'un `FileField` : Django
l'appelle sans argument pour obtenir l'instance et, dans les migrations, ne
sérialise que sa référence d'import (jamais le chemin absolu, qui varie d'un
poste à l'autre — CLAUDE.md : « jamais de chemin absolu en base / migration »).
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class StockagePrive(FileSystemStorage):
    """Stockage sur disque cantonné à `MEDIA_PRIVE_ROOT`, sans URL publique."""

    def __init__(self, **kwargs):
        kwargs.setdefault("location", str(settings.MEDIA_PRIVE_ROOT))
        # Pas de base_url : ces fichiers n'ont pas d'URL publique directe.
        kwargs.setdefault("base_url", None)
        super().__init__(**kwargs)
