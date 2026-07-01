#!/usr/bin/env bash
#
# deploy.sh — Déploiement de l'application Django de l'association
#
# Exécuté sur le VPS Infomaniak, déclenché par le récepteur de webhook
# (webhook_receiver.py) après un push sur la branche surveillée.
#
# Principe : on tire les derniers changements, on met à jour
# dépendances / base / fichiers statiques, puis on redémarre Gunicorn.
# Chaque étape est journalisée et toute erreur interrompt le script.
#
# --- Réglages (à adapter à ton installation) -------------------------
set -euo pipefail

APP_DIR="/srv/asso/app"                 # dépôt git de l'application
VENV_DIR="/srv/asso/venv"               # environnement virtuel Python
BRANCH="main"                           # branche déployée
GUNICORN_SERVICE="asso"                 # nom du service systemd Gunicorn
LOG_FILE="/srv/asso/logs/deploy.log"    # journal des déploiements
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

# --- Journalisation ---------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "──────────────────────────────────────────────"
log "Début du déploiement (branche : $BRANCH)"

cd "$APP_DIR"

# --- 1. Récupération du code -----------------------------------------
# On force l'alignement sur la branche distante pour éviter les conflits
# de merge sur un serveur (le VPS ne doit jamais avoir de commits locaux).
log "Récupération des changements depuis GitHub…"
git fetch --all --quiet
git checkout "$BRANCH" --quiet
git reset --hard "origin/$BRANCH" --quiet
COMMIT=$(git rev-parse --short HEAD)
log "Code aligné sur le commit $COMMIT"

# --- 2. Dépendances ---------------------------------------------------
# On n'installe que si requirements.txt a changé depuis le dernier déploiement.
if git diff --name-only "HEAD@{1}" HEAD 2>/dev/null | grep -q "requirements.txt"; then
    log "requirements.txt modifié → installation des dépendances…"
    "$PIP" install --quiet --upgrade pip
    "$PIP" install --quiet -r requirements.txt
else
    log "Dépendances inchangées, étape ignorée."
fi

# --- 3. Migrations de base de données --------------------------------
log "Application des migrations…"
"$PYTHON" manage.py migrate --noinput

# --- 4. Fichiers statiques -------------------------------------------
log "Collecte des fichiers statiques…"
"$PYTHON" manage.py collectstatic --noinput --clear

# --- 5. Vérification de cohérence ------------------------------------
# Le check Django attrape les erreurs de configuration avant le redémarrage.
log "Vérification de la configuration Django…"
"$PYTHON" manage.py check --deploy

# --- 6. Redémarrage de l'application ----------------------------------
# On redémarre Gunicorn. systemctl est appelé via sudo restreint
# (voir la règle sudoers dans le cahier des charges).
log "Redémarrage de Gunicorn ($GUNICORN_SERVICE)…"
sudo /bin/systemctl restart "$GUNICORN_SERVICE"

log "Déploiement terminé avec succès (commit $COMMIT)."
log "──────────────────────────────────────────────"
