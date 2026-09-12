---
chantier: VIT-4
statut: à venir
---

# VIT-4 — pages artistes expressives : identité commune et page éditée par l'artiste

**Point de départ** — Rien n'est commencé. Un guide externe daté du 12 septembre 2026
cadre le sujet (`docs/guide-refonte-pages-artistes.md`) : une identité Improliante
commune, des pages artistes personnalisables dans des bornes, un brouillon séparé de la
version publique. Le dépôt lui donne raison sur les faits — ses dix références au code
ont été vérifiées une à une — mais il ignore quatre briques déjà en place et laisse deux
arbitrages structurants ouverts. C'est ce que cette fiche tient.

## Reste

### Arbitrages
- [ ] Trancher entre étendre `Moderation` à `Membre` et poser une révision versionnée (`PageArtiste` / `RevisionPageArtiste`) — c'est ce choix qui décide du coût du chantier : la première option réutilise la mécanique que CLAUDE.md règle 7 impose partout ailleurs, la seconde est la seule qui permette de restaurer une version antérieure
- [ ] Décider si les dérivés d'images entrent dans le périmètre ou restent en GED-03 (v2) — aucun redimensionnement n'existe nulle part aujourd'hui, l'original de 5 Mio part tel quel, et le guide en fait une dépendance de sa fondation technique
- [ ] Arrêter le nombre de fiches artistes réellement concernées — la matrice de droits à cinq colonnes et le verrou de version du guide sont dimensionnés pour un CMS multi-tenant, pas pour une dizaine de pages éditées deux fois l'an
- [ ] Décider qui publie une révision : le bureau seul, ou l'artiste avec une capacité déléguée — dépend de SEC-04, le rôle Bureau étant aujourd'hui trop large pour porter cette délégation
- [ ] Retenir une ou deux compositions d'entrée (portrait éditorial, visuel de création) — chaque variante se recette entièrement, et la seconde double la recette sans doubler le contenu

### Préalables
- [ ] VIT-3 est clos : palette, fond et police arrêtés, panneau DEV retiré — on ne peut pas juger « accueil, artiste et spectacle forment un seul site » tant que l'identité n'est pas arrêtée
- [ ] Le périmètre est réduit à ce qui est décidé ci-dessus et réécrit dans cette fiche — le guide couvre plus large que ce que le dépôt fera, et il le dit lui-même

### Vérifications
- [ ] Un réglage du panneau de confort ne fait plus disparaître les autres classes de `<html>` : `accessibilite.js` ne touche qu'aux classes qui lui appartiennent, et le cookie `a11y` est relu contre une liste fermée
- [ ] Les points d'écriture des champs publics de `Membre` passent tous par le même chemin de publication : `espace_membre/forms.py`, `backoffice/forms.py` et sa vue, les deux constructeurs de `coeur/services.py`, le geste photo, et `MembreAdmin` qui n'a aujourd'hui aucun `fields` restreint
- [ ] Le JSON-LD de `vitrine/seo.py` lit la même source que la page : il ne publie pas une biographie que la page n'affiche pas
- [ ] Un artiste porté à la distribution d'un spectacle mais absent d'une représentation ne voit pas cette date annoncée comme sa participation — seule une `Intervention` explicite sur un événement publié et public la produit
- [ ] Un événement lié à l'artiste mais en visibilité « membres » n'apparaît pas sur sa page publique, ni dans le compte des prochaines dates
- [ ] Une image de brouillon n'est pas lisible sans session : elle vit sous `MEDIA_PRIVE_ROOT` et se sert par une vue qui contrôle les droits, comme les reçus et les documents
- [ ] Aucune requête ne part vers YouTube avant que le visiteur ait cliqué — le même geste que le flux Bluesky de la fiche membre, qui ne charge rien avant le clic

## Contexte

**Mis de côté le 12 septembre 2026**, le jour où le guide est entré au dépôt. Le front
n'est pas le sujet des dernières avancées : SEC-1 et le déploiement le sont. La fiche
existe pour que le document ne reste pas orphelin dans `docs/`, pas pour ouvrir le
chantier.

### Ce que le guide ignore, à son avantage

Quatre briques existent déjà et allègent son plan :

- **Le stockage privé tourne.** `StockagePrive`, `MEDIA_PRIVE_ROOT` et
  `reponse_fichier_prive` (X-Accel-Redirect en production) servent déjà les reçus, les
  factures, les documents et les signatures. Le guide classe « confidentialité illusoire
  des brouillons » en risque **critique** et met la construction d'un stockage privé en
  précondition de sa fondation technique : c'est un branchement, pas une construction.
- **Le chargement au clic a un précédent qui marche.** Le flux Bluesky de
  `membre_detail.html` et `bluesky.js` ne fait aucune requête tierce avant le clic, sur
  cette page précise. Le lecteur YouTube du guide est le même geste.
- **Les variables sémantiques existent.** Quarante-neuf tokens dans `site.css`
  (`--couleur-texte`, `--surface`, `--bordure`, `--rayon`, `--espace`, `--largeur-texte`…).
  Le guide propose de les créer sous d'autres noms (`--public-surface`…) : les renommer
  coûterait cher pour rien, mieux vaut étendre la convention en place.
- **Les polices sont auto-hébergées.** Quatre `.woff2` dans `front/static/fonts/`,
  décision non négociable de VIT-3. Le guide le demande comme un souhait.

### Les deux arbitrages que le guide ne pose pas

Le premier est celui du `Reste` : son circuit de publication (§10.2) est une mécanique
**parallèle** à `apps/common/moderation.py`, qui fait déjà `brouillon → proposé →
publié/refusé` avec `ETATS_MODIFIABLES_PAR_AUTEUR`, `modifie_apres_publication` et la
file « à revoir ». Le guide ne dit nulle part pourquoi elle ne suffirait pas. La réponse
honnête est qu'elle ne sait pas restaurer une version antérieure — reste à savoir si ce
besoin existe pour une dizaine de pages.

Le second est le dimensionnement. Le guide ne donne aucun ordre de grandeur du nombre de
fiches, et cale ses §9 et §10 sur un outil multi-tenant : cinq sections d'édition,
conflit d'onglets, verrou de version, capacité de publication déléguée, restauration de
révision. Il renvoie ça à son lot 0 comme une précision ; c'est un point de bascule.

### Ce qui reste vrai quoi qu'il arrive

Trois constats tiennent indépendamment du chantier, et ils sont dans les vérifications
ci-dessus.

`accessibilite.js` porte un défaut latent réel. `enregistrer()` fait
`html.setAttribute("class", liste.join(" "))` : il écrase **toutes** les classes de
`<html>`, et `classesActuelles()` verse **tout** ce qui traîne dessus dans le cookie
`a11y`. Rien ne casse aujourd'hui, parce que le thème passe par `data-theme` et que rien
d'autre ne pose de classe sur `<html>` — poser le thème artiste en classe suffirait à le
casser. À noter aussi : `base.html` injecte le cookie tel quel dans `class="…"` ;
l'auto-échappement Django bloque l'évasion d'attribut, donc pas de XSS, mais la liste
fermée reste la bonne réponse.

Les champs publics de `Membre` s'écrivent depuis cinq endroits, dont l'admin sans
`fields` restreints, et se lisent depuis un sixième que le guide oublie : `vitrine/seo.py`
fabrique le JSON-LD depuis `bio` et `role_public`. Toute séparation brouillon/public qui
en manque un se contourne par ce chemin-là.

`Intervention` porte déjà un `role` et une contrainte d'unicité `(evenement, membre)`, et
`Evenement` a sa visibilité à trois niveaux plus la modération. La règle stricte du guide
— pas d'héritage depuis la distribution du spectacle — est écrivable en test tel quel sur
le modèle actuel, sans rien ajouter.

### Collisions connues

- **VIT-3** en est le préalable dur, et le chantier hérite de son CSS : `site.css` fait
  103 ko en un seul fichier, et `base.html` est étendu par trente-sept gabarits
  backoffice contre quatorze vitrine. Toute variable touchée se propage aux trois faces.
- **GED-03** (quotas et traitement des fichiers, v2 assumée) porte le pipeline d'images
  que le guide veut appeler depuis sa fondation.
- **SEC-04** (le rôle Bureau trop large) porte la délégation de publication.
- **PERF-01** porte les N+1 d'affiches et les images non redimensionnées.
- **ARCH-02** (modifications concurrentes qui se perdent) porte le verrou de version.
