# Outils installés dans le harnais d'agent

Ce dossier-ci documente ce qui vit dans `.claude/` — **non versionné** (voir
`.gitignore`). Un clone neuf n'a donc pas ces outils : la procédure de
réinstallation est ci-dessous.

## impeccable — détecteur d'anti-motifs d'interface

**Installé le 13 septembre 2026**, version de skill 4.3.1, moteur 4.0.0.

Détecteur de problèmes de design et d'accessibilité sur HTML, CSS, JSX, TSX, Vue
et Svelte : 61 règles déterministes.

### Comment l'interroger utilement

**Le pointer sur les gabarits ne sert à rien.** Ils lient leur feuille de style
par `{% static 'css/site.css' %}` ; l'outil prend le tag pour un chemin, le dit,
et continue :

```
could not read linked stylesheet {% static 'css/site.css' %}
```

Les gabarits web ne portant aucun `<style>` inline, il ne reste plus rien à
lire : **il n'analyse alors aucune page du site**. Un `detect front/templates/`
rend 105 constats qui viennent tous des quatre gabarits PDF, les seuls à
embarquer leur CSS — et il leur applique des règles d'écran (« haute densité de
pixels », « cibles tactiles ») sur du A4 imprimé. D'où leur mise hors champ dans
`.impeccable/config.json`, le seul fichier versionné de cette installation.

**Sur la feuille seule**, `detect front/static/css/site.css` marche, mais ne voit
que ce qui se lit sans DOM : 12 constats.

**Pour qu'il voie le site**, il faut lui donner des pages *rendues* pointant une
vraie feuille voisine. On réutilise le balayage du dépôt plutôt qu'un
`runserver` : `apps.common.tests._pages_sans_parametre(Client())` construit déjà
un jeu de témoins complet (images réelles, spectacle, événement, réunion,
facture) et se connecte en Bureau, donc il atteint les trois faces. Un serveur nu
ne rendrait que des états vides. En substance :

```python
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
django.setup(); setup_test_environment(); setup_databases(verbosity=0, interactive=False)
pages = _pages_sans_parametre(Client())            # 67 pages
# écrire chaque page à côté d'une copie de site.css, en réécrivant le href
```

Puis `detect` sur le dossier obtenu : 639 occurrences, mais **37 constats
distincts** — la même règle retombe sur chaque page. Dédupliquer avant de lire.

Attention à un artefact de cette capture : `settings_test` pose `DEBUG=1`, donc
la page 404 du balayage est celle de **Django**, pas la nôtre. Les constats qui
la nomment (`gray-on-color #666 sur #ffffcc`, le « (404) » à 9,6 px) ne parlent
pas du site.

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

### Ce qu'il faut croire de ses constats

Sur les 37 distincts du passage du 13 septembre 2026, le tri donne ceci.

**Ce qui tient.**

- **Le fond crème** `--canvas: #ece5d8` (66 pages) et **deux des quatre polices
  candidates**, Fraunces et Instrument Serif — Playfair Display et Bricolage
  Grotesque, non. L'outil a donc un avis sur **les deux moitiés de l'arbitrage
  VIT-3**. À verser au dossier, pas à appliquer : le cahier des charges et
  CLAUDE.md ont autorité.
- **Le motif des bordures latérales** (9 endroits) : `border-left` de 3–4 px sur
  rappels, messages, trésorerie, convocations, encarts, cartes-messages, plus la
  barre de `.tuile::before`. La répétition est réelle. Mais elle n'est pas
  partout décorative — sur `.cr-bloc` l'ambre distingue du bordeaux des points
  numérotés, et les messages Django changent de couleur selon la gravité. Seule
  la barre de `.tuile` est pur ornement.
- **Cinq cartes imbriquées** (budget, finances, fichiers, inscriptions).
- **Les étiquettes de groupe du rail** à `0.68rem` = 10,88 px, soit 0,12 px sous
  son plancher de 11 px. Micro-libellé capitales/800/tracké, déjà arbitré pour le
  contraste (voir le commentaire de `--rail-titre`). `0.7rem` passerait sans rien
  changer à l'œil.

**Ce qui est faux, et démontrablement.**

- `border-accent-on-rounded` sur `.onglet` : l'arrondi est `0.5rem 0.5rem 0 0`
  — coins **hauts** — et la bordure est `border-bottom`, arête **basse**, où les
  coins sont carrés. Elles ne se rencontrent jamais.
- `tiny-text` / `undersized-ui-text` à 9,92 px sur l'accroche de l'accueil :
  `.hero__titre .accent` est à `0.62**em**`, donc relatif au parent en
  `clamp(2.2rem, 6vw, 3.6rem)` — soit 22 à 36 px réels. L'outil a lu `em`
  comme `rem`.
- `tight-leading` (×3, gabarits PDF) : la facture ne déclare `line-height`
  qu'une fois, `1.5` sur un `body` en 11 px. Les ratios annoncés sont 16,5 ÷ 18
  et 16,5 ÷ 13 : l'outil fait hériter les **pixels calculés** au lieu du facteur.
  C'est l'inverse de ce que fait un `line-height` sans unité — sa raison d'être.
- `all-caps-body` « 71 caractères » : c'est la **somme** de quatre libellés
  courts (« FACTURE », « Émetteur », « Client », les en-têtes de colonnes). La
  règle dit elle-même de réserver les capitales aux libellés courts.

**Ce qu'il n'a pas vu.** `.message--success` et `.message--error` ne diffèrent
que par `border-left-color`, et `base.html` rend un `<p>` nu, sans icône ni
préfixe. Pas un manquement au 1.4.1 — le texte du message dit ce qui s'est
passé, et `role="status" aria-live="polite"` le porte — mais au coup d'œil, la
gravité ne tient qu'à la couleur.
