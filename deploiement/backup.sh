#!/usr/bin/env bash
#
# backup.sh — Sauvegarde de la base PostgreSQL et des fichiers médias.
#
# À planifier via cron (ex. tous les jours à 3h) :
#   0 3 * * * /srv/asso/backup.sh >> /srv/asso/logs/backup.log 2>&1
#
# IMPORTANT : la copie hors VPS (Swiss Backup / autre) est l'étape qui
# protège réellement les données. Une sauvegarde qui reste sur le VPS
# disparaît avec lui. La section "envoi distant" ci-dessous est à activer
# selon l'outil choisi (rclone vers Swiss Backup recommandé).
set -euo pipefail

# --- Réglages ---------------------------------------------------------
DB_NAME="asso"
DB_USER="asso"
# Ces deux chemins DOIVENT suivre les settings Django (`MEDIA_ROOT` et
# `MEDIA_PRIVE_ROOT` = BASE_DIR / "media" et "media_prive", BASE_DIR étant
# /srv/asso/app). Se tromper ici ne lève aucune alerte : tar échoue, le script
# s'arrête, et l'envoi hors VPS ne part jamais.
MEDIA_DIR="/srv/asso/app/media"              # médias PUBLICS (affiches, photos)
MEDIA_PRIVE_DIR="/srv/asso/app/media_prive"  # PRIVÉS : factures, reçus fiscaux, docs membres
BACKUP_DIR="/srv/asso/backups"          # destination locale temporaire
RETENTION_JOURS=14                      # purge des sauvegardes locales
HORODATAGE=$(date '+%Y%m%d-%H%M%S')

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%F %T')] Début de la sauvegarde ($HORODATAGE)"

# --- 1. Base de données (dump compressé) ------------------------------
# `pg_dump -U` ne demande pas de mot de passe ici : le cron n'a pas de
# terminal pour en saisir un. Deux options, à trancher à l'installation —
# planifier ce script dans la crontab de l'utilisateur `postgres` (qui passe
# par l'authentification peer, sans mot de passe), ou déposer un fichier
# ~/.pgpass en 0600 pour l'utilisateur qui le lance. Sans l'un des deux, la
# sauvegarde échoue chaque nuit en silence.
DUMP_FILE="$BACKUP_DIR/db-$HORODATAGE.sql.gz"
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DUMP_FILE"
echo "  Base sauvegardée : $DUMP_FILE"

# --- 2. Fichiers médias (archive) -------------------------------------
# Les DEUX arborescences, publique et privée. Oublier la privée reviendrait à
# ne pas sauvegarder les factures, les reçus fiscaux et les documents des
# membres — précisément ce qu'on ne peut pas régénérer.
MEDIA_FILE="$BACKUP_DIR/media-$HORODATAGE.tar.gz"
tar -czf "$MEDIA_FILE" \
    -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")" \
    -C "$(dirname "$MEDIA_PRIVE_DIR")" "$(basename "$MEDIA_PRIVE_DIR")"
echo "  Médias publics et privés sauvegardés : $MEDIA_FILE"

# --- 3. Envoi hors VPS ------------------------------------------------
# L'externalisation est demandée dès le départ (cahier §14) : une sauvegarde
# qui reste sur le VPS disparaît avec le VPS. Le script REFUSE donc de se
# terminer en silence tant que `RCLONE_REMOTE` n'est pas renseigné — sans quoi
# on croit sauvegarder pendant des mois, et on ne le découvre qu'au sinistre.
#
# Renseigner le remote une fois rclone configuré :
#   RCLONE_REMOTE="swissbackup:asso"   (ou export dans l'environnement du cron)
RCLONE_REMOTE="${RCLONE_REMOTE:-}"

if [ -n "$RCLONE_REMOTE" ]; then
    rclone copy "$DUMP_FILE"  "$RCLONE_REMOTE/db/"
    rclone copy "$MEDIA_FILE" "$RCLONE_REMOTE/media/"
    echo "  Sauvegardes envoyées vers $RCLONE_REMOTE"
else
    echo "  ATTENTION : RCLONE_REMOTE vide — sauvegardes gardées SUR LE VPS," >&2
    echo "  donc perdues avec lui. Configurer rclone (cahier §14)." >&2
fi

# --- 4. Purge des anciennes sauvegardes locales -----------------------
find "$BACKUP_DIR" -name "db-*.sql.gz"   -mtime +"$RETENTION_JOURS" -delete
find "$BACKUP_DIR" -name "media-*.tar.gz" -mtime +"$RETENTION_JOURS" -delete
echo "  Purge des sauvegardes de plus de $RETENTION_JOURS jours effectuée."

echo "[$(date '+%F %T')] Sauvegarde terminée."
