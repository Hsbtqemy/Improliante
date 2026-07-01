"""Service de fichiers privés : réponse HTTP contrôlée pour un fichier stocké
hors racine web.

Deux modes selon l'environnement (réglage `settings.UTILISER_X_ACCEL`) :

- **Production** : on renvoie une réponse vide portant l'en-tête
  `X-Accel-Redirect`. Django s'est contenté de vérifier les droits ; c'est
  Nginx qui sert réellement le fichier depuis sa location `internal`
  (performant, le fichier ne transite pas par Python).
- **Développement** : Django sert lui-même le fichier via `FileResponse`.

Dans les deux cas l'appelant DOIT avoir vérifié l'autorisation en amont : ce
helper ne fait aucun contrôle de droits, il ne fait que produire la réponse.
"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import File
from django.http import FileResponse, HttpResponse


def reponse_fichier_prive(
    fichier: File,
    *,
    nom_telechargement: str | None = None,
    inline: bool = False,
) -> HttpResponse:
    """Construit la réponse de téléchargement d'un `fichier` (FieldFile).

    - `nom_telechargement` : nom présenté à l'utilisateur (défaut : nom réel).
    - `inline` : affichage dans le navigateur plutôt que téléchargement.
    """
    nom = nom_telechargement or PurePosixPath(fichier.name).name
    type_mime = mimetypes.guess_type(nom)[0] or "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    # RFC 6266 : filename*=UTF-8'' pour préserver les accents des noms.
    entete_disposition = f"{disposition}; filename*=UTF-8''{quote(nom)}"

    if getattr(settings, "UTILISER_X_ACCEL", False):
        reponse = HttpResponse(content_type=type_mime)
        # Le chemin est relatif au stockage ; Nginx le résout dans sa location
        # `internal` pointant vers MEDIA_PRIVE_ROOT.
        reponse["X-Accel-Redirect"] = settings.X_ACCEL_PREFIXE + quote(fichier.name)
        reponse["Content-Disposition"] = entete_disposition
        return reponse

    reponse = FileResponse(fichier.open("rb"), content_type=type_mime)
    reponse["Content-Disposition"] = entete_disposition
    return reponse
