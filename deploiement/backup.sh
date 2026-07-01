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
MEDIA_DIR="/srv/asso/media"             # fichiers uploadés (affiches, docs)
BACKUP_DIR="/srv/asso/backups"          # destination locale temporaire
RETENTION_JOURS=14                      # purge des sauvegardes locales
HORODATAGE=$(date '+%Y%m%d-%H%M%S')

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%F %T')] Début de la sauvegarde ($HORODATAGE)"

# --- 1. Base de données (dump compressé) ------------------------------
DUMP_FILE="$BACKUP_DIR/db-$HORODATAGE.sql.gz"
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DUMP_FILE"
echo "  Base sauvegardée : $DUMP_FILE"

# --- 2. Fichiers médias (archive) -------------------------------------
MEDIA_FILE="$BACKUP_DIR/media-$HORODATAGE.tar.gz"
tar -czf "$MEDIA_FILE" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"
echo "  Médias sauvegardés : $MEDIA_FILE"

# --- 3. Envoi hors VPS (À ACTIVER) ------------------------------------
# Exemple avec rclone configuré sur un remote "swissbackup" :
#   rclone copy "$DUMP_FILE"   swissbackup:asso/db/
#   rclone copy "$MEDIA_FILE"  swissbackup:asso/media/
# echo "  Sauvegardes envoyées vers le stockage distant."

# --- 4. Purge des anciennes sauvegardes locales -----------------------
find "$BACKUP_DIR" -name "db-*.sql.gz"   -mtime +"$RETENTION_JOURS" -delete
find "$BACKUP_DIR" -name "media-*.tar.gz" -mtime +"$RETENTION_JOURS" -delete
echo "  Purge des sauvegardes de plus de $RETENTION_JOURS jours effectuée."

echo "[$(date '+%F %T')] Sauvegarde terminée."
