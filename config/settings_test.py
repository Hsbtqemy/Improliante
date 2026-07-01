"""Réglages Django pour les tests : base SQLite en mémoire, hachage rapide.

On force `DJANGO_DEBUG` avant l'import des settings de base pour que la clé
secrète de repli s'applique — ainsi les tests tournent sans `.env` (utile en CI).

Nuance : SQLite ne supporte pas `select_for_update` (no-op). Les tests valident
donc les règles fonctionnelles ; la sûreté concurrentielle repose sur PostgreSQL.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("DJANGO_DEBUG", "1")

from config.settings import *  # noqa: E402, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Hachage rapide pour accélérer les tests (pas d'Argon2 ici).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Médias cantonnés dans un dossier temporaire : les tests qui écrivent des
# fichiers (uploads, stockage privé) ne polluent jamais le dépôt.
_MEDIA_TMP = Path(tempfile.mkdtemp(prefix="improliante-test-media-"))
MEDIA_ROOT = _MEDIA_TMP / "public"
MEDIA_PRIVE_ROOT = _MEDIA_TMP / "prive"

# On teste par défaut le service direct par Django (FileResponse) ; le chemin
# X-Accel-Redirect est couvert par un test dédié qui bascule ce réglage.
UTILISER_X_ACCEL = False
