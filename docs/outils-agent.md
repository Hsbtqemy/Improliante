# Outils installés dans le harnais d'agent

Ce dossier-ci documente ce qui vit dans `.claude/` — **non versionné** (voir
`.gitignore`). Un clone neuf n'a donc pas ces outils : la procédure de
réinstallation est ci-dessous.

## impeccable — détecteur d'anti-motifs d'interface

**Installé le 13 septembre 2026**, version de skill 4.3.1, moteur 4.0.0.

Détecteur de problèmes de design et d'accessibilité sur HTML, CSS, JSX, TSX, Vue
et Svelte : 61 règles déterministes. Sur ce dépôt, il vise `front/static/css/` et
`front/templates/`. Il s'appelle à la demande :

```bash
sh .claude/skills/impeccable/scripts/impeccable detect front/static/css/site.css
sh .claude/skills/impeccable/scripts/impeccable detect front/templates/vitrine/
```

### Réinstaller

L'installeur officiel (`npx impeccable skills install`) **ne fonctionne pas** en
4.1.0 : son `downloadFile` ne suit qu'une seule redirection et ne vérifie pas le
statut de la seconde. Or `impeccable.style/api/download/bundle/universal` en fait
deux (→ GitHub Releases → stockage d'objets). Le corps de la seconde redirection,
vide, est écrit dans le fichier, et la promesse est résolue comme un succès :
on obtient une archive de 0 octet, puis une erreur `unzip` incompréhensible.

D'ici là, l'installation se fait à la main :

```bash
curl -sSL -o /tmp/universal.zip https://impeccable.style/api/download/bundle/universal
unzip -qo /tmp/universal.zip -d /tmp/impeccable
cp -r /tmp/impeccable/.claude .
rm -f .claude/settings.json          # voir « Sans les hooks » ci-dessous
```

Le moteur binaire, lui, se télécharge tout seul au premier appel du lanceur, dans
`~/.impeccable/bin/` — ce chemin-là marche.

### Deux écarts assumés par rapport à l'installation par défaut

**Non versionné.** Le paquet pèse 2,2 Mo pour 55 fichiers, dont un index de
polices de 1,1 Mo et un script de navigateur de 522 ko. Ce sont des assets
vendus, réinstallables en une commande ; ils n'ont pas de raison d'entrer dans
l'historique d'un dépôt Django, et personne d'autre ne travaille sur ce clone.

**Sans les hooks.** Le `settings.json` fourni pose deux crochets Claude Code :
une commande après chaque `Edit`/`Write` (5 s) et une autre à la fin de chaque
tour (30 s). Il n'est pas installé. Le détecteur ne concerne ni Python, ni les
migrations, ni les tests — c'est-à-dire l'essentiel de ce qui s'écrit ici — et
chaque lot passe déjà par `pytest`, `ruff`, `manage.py check` et des sondes.
L'appeler quand on touche au front est un geste, pas un automatisme.

### Ce qu'il a trouvé au premier passage

Douze constats sur `site.css` : neuf `side-tab` (bordure colorée épaisse sur un
seul côté d'une carte), un `border-accent-on-rounded`, et **deux polices jugées
surexposées — Fraunces et Instrument Serif**. Ces deux-là sont parmi les quatre
candidates que VIT-3 doit départager : à verser au dossier de cet arbitrage, pas
à appliquer tel quel. L'outil a un avis, le cahier des charges et CLAUDE.md ont
autorité.
