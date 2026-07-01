#!/usr/bin/env python3
"""
webhook_receiver.py — Récepteur de webhook GitHub pour le VPS de l'association.

Écoute les requêtes POST envoyées par GitHub à chaque push, vérifie leur
signature (secret partagé HMAC-SHA256), et déclenche deploy.sh si le push
concerne la bonne branche.

Sécurité :
  - La signature GitHub (en-tête X-Hub-Signature-256) est vérifiée AVANT
    tout traitement. Une requête non signée ou mal signée est rejetée.
  - On ne déploie que la branche surveillée (par défaut : main).
  - Le secret est lu depuis une variable d'environnement, jamais codé en dur.

Déploiement de ce service : voir le service systemd dans le cahier des charges.
Il tourne en local (127.0.0.1) derrière Nginx, qui expose /webhook en HTTPS.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Configuration (depuis l'environnement) --------------------------------
SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").encode()
DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", "/srv/asso/deploy.sh")
WATCHED_BRANCH = os.environ.get("WATCHED_BRANCH", "main")
LISTEN_HOST = os.environ.get("WEBHOOK_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
LOG_FILE = os.environ.get("WEBHOOK_LOG", "/srv/asso/logs/webhook.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("webhook")


def signature_valide(corps: bytes, signature_entete: str) -> bool:
    """Vérifie la signature HMAC-SHA256 envoyée par GitHub."""
    if not SECRET:
        log.error("Aucun secret configuré (GITHUB_WEBHOOK_SECRET) — rejet.")
        return False
    if not signature_entete or not signature_entete.startswith("sha256="):
        return False
    attendue = "sha256=" + hmac.new(SECRET, corps, hashlib.sha256).hexdigest()
    # compare_digest évite les attaques par analyse de temps de réponse
    return hmac.compare_digest(attendue, signature_entete)


class WebhookHandler(BaseHTTPRequestHandler):
    def _repondre(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._repondre(404, "Not found")
            return

        longueur = int(self.headers.get("Content-Length", 0))
        corps = self.rfile.read(longueur)

        # 1. Vérification de la signature (sécurité prioritaire)
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not signature_valide(corps, signature):
            log.warning("Signature invalide — requête rejetée (IP %s).",
                        self.client_address[0])
            self._repondre(403, "Signature invalide")
            return

        # 2. On ne traite que les événements de push
        evenement = self.headers.get("X-GitHub-Event", "")
        if evenement == "ping":
            log.info("Ping reçu de GitHub — webhook opérationnel.")
            self._repondre(200, "pong")
            return
        if evenement != "push":
            log.info("Événement '%s' ignoré.", evenement)
            self._repondre(200, "Événement ignoré")
            return

        # 3. Filtrage sur la branche surveillée
        try:
            charge = json.loads(corps)
        except json.JSONDecodeError:
            self._repondre(400, "JSON invalide")
            return

        ref = charge.get("ref", "")
        if ref != f"refs/heads/{WATCHED_BRANCH}":
            log.info("Push sur %s ignoré (on surveille %s).", ref, WATCHED_BRANCH)
            self._repondre(200, "Branche ignorée")
            return

        # 4. Déclenchement du déploiement
        log.info("Push valide sur %s — lancement du déploiement.", WATCHED_BRANCH)
        try:
            resultat = subprocess.run(
                ["/usr/bin/env", "bash", DEPLOY_SCRIPT],
                capture_output=True, text=True, timeout=600,
            )
            if resultat.returncode == 0:
                log.info("Déploiement réussi.")
                self._repondre(200, "Déploiement réussi")
            else:
                log.error("Échec du déploiement :\n%s", resultat.stderr)
                self._repondre(500, "Échec du déploiement")
        except subprocess.TimeoutExpired:
            log.error("Déploiement interrompu (timeout).")
            self._repondre(500, "Timeout du déploiement")

    def log_message(self, *args):
        # On désactive le log par défaut (bruyant) au profit du nôtre.
        return


def main() -> None:
    if not SECRET:
        log.error("GITHUB_WEBHOOK_SECRET manquant. Arrêt.")
        sys.exit(1)
    serveur = HTTPServer((LISTEN_HOST, LISTEN_PORT), WebhookHandler)
    log.info("Récepteur de webhook démarré sur %s:%s (branche : %s).",
             LISTEN_HOST, LISTEN_PORT, WATCHED_BRANCH)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        log.info("Arrêt du récepteur de webhook.")
        serveur.server_close()


if __name__ == "__main__":
    main()
