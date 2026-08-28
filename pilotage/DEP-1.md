---
chantier: DEP-1
statut: à venir
---

# DEP-1 — déploiement VPS

**Point de départ** — Les six fichiers de `deploiement/` sont écrits et relus (`deploy.sh`,
`webhook_receiver.py`, `asso.service`, `asso-webhook.service`, `nginx-improliante.conf`,
`backup.sh`). Aucun n'a jamais tourné sur une machine : rien n'est provisionné côté VPS
Infomaniak, et le chantier commence au premier `ssh`. C'est le seul reste de la v1.

## Reste

### Serveur
- [ ] PostgreSQL répond sur le VPS, avec la base et le rôle de l'application créés — `psql -c 'select version()'` sort une version, pas une erreur de socket
- [ ] Les libs natives de WeasyPrint sont installées (libpango, libcairo, libgdk-pixbuf, libffi) — `python -c "import weasyprint"` passe sans trace d'appel manquant
- [ ] L'utilisateur `deploy` existe et possède `/srv/asso/{app,venv,run,logs}`, groupe `www-data` — l'arborescence attendue par `asso.service`

### Application
- [ ] `/srv/asso/app.env` porte `DJANGO_SECRET_KEY` et les `DB_*`, en mode 0600, hors dépôt — règle 3 de CLAUDE.md, vérifiée par un `git check-ignore` et un `stat`
- [ ] `DEBUG` vaut False en production et `manage.py check --deploy` sort sans avertissement — règle 6 de CLAUDE.md
- [ ] `manage.py migrate` puis `collectstatic --noinput` passent sur le VPS, et Nginx sert bien le `STATIC_ROOT` produit
- [ ] `systemctl enable --now asso` laisse le service `active (running)` et le socket `/srv/asso/run/gunicorn.sock` présent

### Réseau et TLS
- [ ] Nginx joint Gunicorn par le socket Unix — une requête sur `/` rend 200 avec le HTML de l'accueil, pas une 502
- [ ] Certbot a délivré le certificat : `https://<domaine>` est valide et le HTTP répond 301 vers HTTPS
- [ ] La `location` interne X-Accel sert un fichier privé : le propriétaire reçoit le fichier, un autre membre connecté reçoit 403 et jamais l'octet — règles 1 et 5 de CLAUDE.md

### Déploiement continu
- [ ] `asso-webhook.service` tourne et un push sur `main` déclenche `deploy.sh` : `/srv/asso/logs/deploy.log` porte le hash du commit déployé
- [ ] Une requête au webhook portant une signature HMAC fausse est rejetée en 403 et laisse une trace dans le journal

### Sauvegardes
- [ ] `backup.sh` tourne en cron et dépose un dump daté sur Swiss Backup — l'externalisation est demandée dès le départ (cahier §14)
- [ ] Une restauration d'essai repart d'un dump : la base restaurée porte les dernières adhésions, pas un schéma vide

## Contexte

Le déploiement est le seul module de la v1 qui n'ait jamais été exécuté. Tout le reste
de l'application est implémenté et testé (~168 tests verts) ; ici, rien n'a été confronté
à une vraie machine, et c'est précisément ce que les items ci-dessus demandent de faire.

Trois règles non négociables de CLAUDE.md se jouent sur ce chantier, et aucune n'est
testable depuis le poste de développement : les secrets hors Git (3), les fichiers privés
servis par une vue authentifiée ou X-Accel (5), et `DEBUG = False` avec `check --deploy`
qui passe (6). Elles ont chacune leur case.

`deploy.sh` fait un `git reset --hard origin/main` : le VPS ne doit jamais porter de
commit local. À garder en tête si un correctif est tenté directement sur le serveur — il
sera écrasé au déploiement suivant, sans avertissement.
