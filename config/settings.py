"""
Réglages Django du projet « config » (application de l'association).

Configuration pilotée par variables d'environnement (principe 12-factor) :
les secrets et paramètres sensibles ne sont JAMAIS écrits en dur ici.
- En développement : un fichier `.env` (non versionné) est chargé si
  python-dotenv est installé (cf. `.env.example`).
- En production : les variables sont fournies par systemd (EnvironmentFile,
  cf. deploiement/asso.service), jamais par un `.env`.

Doc : https://docs.djangoproject.com/en/6.0/topics/settings/
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# BASE_DIR = racine du dépôt (contient manage.py, apps/, config/, front/).
BASE_DIR = Path(__file__).resolve().parent.parent

# Chargement optionnel d'un fichier .env en développement. python-dotenv est
# une dépendance de confort : s'il est absent, on lit directement
# l'environnement du processus (cas de la production servie par systemd).
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    pass
else:
    load_dotenv(BASE_DIR / ".env")


def env_bool(nom: str, defaut: bool = False) -> bool:
    """Lit une variable d'environnement booléenne (« 1 », « true », « yes », « on »)."""
    valeur = os.environ.get(nom)
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "yes", "on"}


def env_list(nom: str, defaut: str = "") -> list[str]:
    """Lit une variable d'environnement en liste (séparateur : virgule)."""
    return [item.strip() for item in os.environ.get(nom, defaut).split(",") if item.strip()]


# --- Sécurité de base -------------------------------------------------------

# SECURITY WARNING: le mode debug ne doit JAMAIS être actif en production.
DEBUG = env_bool("DJANGO_DEBUG", False)

# SECURITY WARNING: la clé secrète provient de l'environnement.
# En dev, une clé de repli est tolérée ; en prod, son absence est fatale.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-key-a-remplacer-en-production"  # noqa: S105
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY est obligatoire lorsque DEBUG est désactivé.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


# --- Applications -----------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# Bibliothèques tierces — à décommenter au fur et à mesure de leur
# installation (voir requirements.txt). Laissées inactives à l'amorçage
# pour que le squelette tourne avec Django seul.
THIRD_PARTY_APPS: list[str] = [
    # "rest_framework",                 # API (DRF)
    "treebeard",  # arbres GED (Dossier auto-référent)
    # "guardian",                       # permissions par objet
    # "axes",                           # anti-brute-force
    # "django_otp",                     # 2FA
    # "django_otp.plugins.otp_totp",
    # "csp",                            # en-têtes Content-Security-Policy
    # "simple_history",                 # journal d'audit
]

# Apps métier — une app par domaine (cf. docs/cahier-des-charges-asso.md §16).
# `apps.common` : abstraits techniques partagés (Horodatage, Moderation).
LOCAL_APPS = [
    "apps.common",
    "apps.coeur",
    "apps.spectacles",
    "apps.agenda",
    "apps.medias",
    "apps.documents",
    "apps.facturation",
    "apps.budget",
    "apps.gouvernance",
    "apps.vitrine",  # front public (rendu serveur)
    "apps.espace_membre",  # espace membre connecté
    "apps.backoffice",  # back-office bureau (modération, GED, facturation…)
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "front" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.backoffice.context_processors.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --- Base de données --------------------------------------------------------
# PostgreSQL (choix arrêté, cf. §2). Les identifiants viennent de
# l'environnement ; les valeurs par défaut correspondent à deploiement/backup.sh.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "asso"),
        "USER": os.environ.get("DB_USER", "asso"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        # connect_timeout borne l'attente quand la base est injoignable
        # (utile en dev hors-ligne : makemigrations / check échouent vite).
        "OPTIONS": {"connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))},
    }
}


# --- Authentification / mots de passe --------------------------------------
# Modèle utilisateur custom dès la v1 (extensible sans migration lourde).
AUTH_USER_MODEL = "coeur.Utilisateur"

# Espace membre : redirections d'authentification.
LOGIN_URL = "espace_membre:connexion"
LOGIN_REDIRECT_URL = "espace_membre:tableau_de_bord"
LOGOUT_REDIRECT_URL = "vitrine:accueil"

# Hachage Argon2 imposé (cf. §10). Nécessite argon2-cffi (requirements.txt).

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True


# --- Fichiers statiques et médias ------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # cible de collectstatic (prod)
STATICFILES_DIRS = [BASE_DIR / "front" / "static"]  # assets du front public

# Médias uploadés. `MEDIA_ROOT` (servi publiquement par Nginx) ne contient que
# des fichiers destinés au public. Les fichiers PRIVÉS (factures, reçus fiscaux,
# pièces membres, documents confidentiels) vont dans `MEDIA_PRIVE_ROOT`, hors
# racine web, et ne sont servis QUE par une vue authentifiée contrôlant les
# droits (cf. apps.common.fichiers) — jamais par URL publique devinable.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Stockage privé : hors racine web publique. En production, Nginx expose ce
# dossier via une location `internal` (X-Accel-Redirect) accessible uniquement
# après contrôle des droits côté Django.
MEDIA_PRIVE_ROOT = Path(os.environ.get("DJANGO_MEDIA_PRIVE_ROOT", BASE_DIR / "media_prive"))

# Service des fichiers privés :
# - en production, on délègue l'envoi à Nginx via l'en-tête X-Accel-Redirect
#   (Django ne fait que contrôler les droits, Nginx sert le fichier) ;
# - en développement, Django sert lui-même le fichier (FileResponse).
UTILISER_X_ACCEL = env_bool("DJANGO_X_ACCEL", not DEBUG)
# Préfixe de la location `internal` Nginx pointant vers MEDIA_PRIVE_ROOT.
X_ACCEL_PREFIXE = os.environ.get("DJANGO_X_ACCEL_PREFIXE", "/media-prive/")


# --- Divers -----------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- E-mail -----------------------------------------------------------------
# Envoi non activé pour l'instant : backend console en dev. Les messages de
# contact sont persistés en base (admin) plutôt qu'envoyés. Pour activer l'envoi
# (SMTP), renseigner DJANGO_EMAIL_BACKEND + EMAIL_* + CONTACT_EMAIL dans app.env.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@improliante.example")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")


# --- Durcissement en production --------------------------------------------
# Actif uniquement hors debug. `manage.py check --deploy` doit passer en prod.

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
