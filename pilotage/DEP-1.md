---
chantier: DEP-1
statut: interrompu
---

# DEP-1 — déploiement VPS

**Arrêté sur** — audit des six fichiers de `deploiement/` face à `config/settings.py`,
six défauts corrigés dont quatre bloquants, commit `1146628`, 28 août. Rien n'est encore
provisionné côté VPS Infomaniak : la suite commence au premier `ssh`.

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
- [ ] GitHub affiche la livraison en vert : le récepteur répond `202` en moins de dix secondes, sans attendre la fin du déploiement
- [ ] Un second push pendant un déploiement laisse « Déploiement déjà en cours » dans `deploy.log` au lieu de lancer un doublon — `flock` n'existe pas sur macOS, ce verrou n'a jamais été exécuté
- [ ] Le socket sort bien en 0770 (`ls -l /srv/asso/run/gunicorn.sock`) : c'est `--umask 007` qui l'obtient, et son absence donnait un 502 systématique

### Sauvegardes
- [ ] `backup.sh` tourne en cron et dépose un dump daté sur Swiss Backup — l'externalisation est demandée dès le départ (cahier §14)
- [ ] Une restauration d'essai repart d'un dump : la base restaurée porte les dernières adhésions, pas un schéma vide
- [ ] L'archive des médias contient `media` **et** `media_prive` — `tar tzf` le montre ; sans le privé, ni facture ni reçu fiscal n'est sauvegardé
- [ ] `RCLONE_REMOTE` est renseigné : sans lui le script crie sur stderr et les sauvegardes restent sur le VPS

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

## Audit du 28 août (avant toute machine)

Les six fichiers ont été relus ligne à ligne et croisés avec `config/settings.py`. Six
défauts corrigés, dont quatre auraient empêché la mise en ligne et deux auraient coûté
des données. Le détail vit dans le message de `1146628` ; ce qu'il faut retenir ici,
c'est que **chacun se serait manifesté par un symptôme trompeur** :

- Socket Gunicorn en 0755 faute d'`--umask 007` → 502 sur toutes les requêtes, avec pour
  seul indice un « permission denied » dans le log d'erreur de Nginx.
- `NoNewPrivileges=true` sur le service qui lance `deploy.sh` → le `sudo systemctl` final
  échoue, à chaque déploiement, tout à la fin.
- Aucune route Nginx vers le récepteur de webhook → GitHub ne peut pas l'atteindre.
- Récepteur synchrone (timeout 600 s) contre une coupure GitHub vers 10 s → le webhook
  passe au rouge pendant que le déploiement réussit.
- `backup.sh` sur le mauvais chemin de médias, et sans `media_prive` du tout.
- Envoi hors VPS en commentaire, alors que le cahier §14 le demande dès le départ.

Rien de tout cela n'a été **exécuté** : la syntaxe bash et Python est vérifiée, mais
`flock` n'existe pas sur macOS et aucune de ces lignes n'a touché un serveur. Les cases
ci-dessus restent donc entières — l'audit réduit le risque, il ne le remplace pas.

Ce qu'il faut pour reprendre : un VPS joignable en `ssh`, un nom de domaine pointant
dessus, et les valeurs de `app.env` (`DJANGO_SECRET_KEY`, `DB_*`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`).
