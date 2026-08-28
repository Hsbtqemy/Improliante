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

# --- Dossiers de travail ----------------------------------------------
# À créer AVANT le premier `tee` : sinon la toute première ligne de journal
# fait échouer le script (set -e) sans rien écrire nulle part.
LOCK_FILE="/srv/asso/run/deploy.lock"
mkdir -p "$(dirname "$LOCK_FILE")" "$(dirname "$LOG_FILE")"

# --- Verrou -----------------------------------------------------------
# Deux pushes rapprochés lancent deux déploiements ; sans verrou ils se
# marchent dessus (migrations concurrentes, collectstatic à moitié écrit).
# Le descripteur 9 reste ouvert jusqu'à la fin du script : le verrou tombe
# avec lui, y compris si le script meurt en route.
#
# Le second passage renonce plutôt qu'il n'attend. C'est sans perte dans le
# cas courant — celui qui tourne fait `git reset --hard origin/main` et
# emporte donc aussi les commits du second push. Si le premier a déjà dépassé
# son `fetch`, le dernier push attendra le suivant : pousser à nouveau, ou
# relancer le script à la main, suffit à rattraper.
exec 9>"$LOCK_FILE"
if ! flock --nonblock 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Déploiement déjà en cours — abandon." >>"$LOG_FILE"
    exit 0
fi

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
# Retenu AVANT le reset : sert à savoir ce qui a bougé. `|| echo ""` couvre le
# tout premier déploiement, où il n'y a pas encore de HEAD exploitable.
COMMIT_AVANT=$(git rev-parse HEAD 2>/dev/null || echo "")
git fetch --all --quiet
git checkout "$BRANCH" --quiet
git reset --hard "origin/$BRANCH" --quiet
COMMIT=$(git rev-parse --short HEAD)
log "Code aligné sur le commit $COMMIT"

# --- 2. Dépendances ---------------------------------------------------
# On n'installe que si requirements.txt a bougé — mais TOUJOURS au premier
# déploiement, quand il n'y a pas d'état antérieur à comparer. L'ancienne
# version interrogeait le reflog (`HEAD@{1}`), vide au premier passage : la
# comparaison échouait en silence et concluait « dépendances inchangées » sur
# un venv encore nu.
if [ -z "$COMMIT_AVANT" ] || ! git diff --quiet "$COMMIT_AVANT" HEAD -- requirements.txt; then
    log "Installation des dépendances…"
    "$PIP" install --quiet --upgrade pip
    "$PIP" install --quiet -r requirements.txt
else
    log "Dépendances inchangées, étape ignorée."
fi

# --- 3. Vérification de cohérence ------------------------------------
# AVANT de toucher à la base : une configuration invalide doit arrêter le
# déploiement pendant qu'il est encore sans effet, pas après des migrations
# déjà appliquées. `--fail-level WARNING` parce que la règle 6 du projet exige
# que `check --deploy` sorte SANS avertissement : sans ce niveau, la commande
# rend 0 en signalant des faiblesses de sécurité, et ne bloque donc rien.
log "Vérification de la configuration Django…"
"$PYTHON" manage.py check --deploy --fail-level WARNING

# --- 4. Migrations de base de données --------------------------------
log "Application des migrations…"
"$PYTHON" manage.py migrate --noinput

# --- 5. Fichiers statiques -------------------------------------------
log "Collecte des fichiers statiques…"
"$PYTHON" manage.py collectstatic --noinput --clear

# --- 6. Redémarrage de l'application ----------------------------------
# On redémarre Gunicorn. systemctl est appelé via sudo restreint
# (voir la règle sudoers dans le cahier des charges).
log "Redémarrage de Gunicorn ($GUNICORN_SERVICE)…"
sudo /bin/systemctl restart "$GUNICORN_SERVICE"

log "Déploiement terminé avec succès (commit $COMMIT)."
log "──────────────────────────────────────────────"
