"""Réglages Django pour les tests : base SQLite en mémoire, hachage rapide.

On force `DJANGO_DEBUG` avant l'import des settings de base pour que la clé
secrète de repli s'applique — ainsi les tests tournent sans `.env` (utile en CI).

Nuance : SQLite ne supporte pas `select_for_update` (no-op). Les tests valident
donc les règles fonctionnelles ; la sûreté concurrentielle repose sur PostgreSQL.
"""

import os

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
