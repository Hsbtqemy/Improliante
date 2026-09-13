---
passe: Identité visuelle — fond et police de titre
chantier: VIT-3
duree: 45 min
derniere: —
---

# QA — arrêter le fond et la police de titre

VIT-3 tient trois chantiers en otage : ses deux arbitrages non tranchés bloquent
le retrait du panneau DEV, toute la mise en production de la fonte, et quatre cas
de VIT-4. Aucun ne se décide au clavier — le guide de refonte est explicite :
le choix « doit être évalué sur l'accueil, une page artiste et une page spectacle
**ensemble**, avec de vrais contenus ».

Cette passe est faite pour que cette évaluation prenne 45 minutes et laisse une
décision écrite, pas une impression.

## Lancer le site

```bash
venv/Scripts/python.exe manage.py runserver --settings=local_settings
```

La base SQLite locale est peuplée : 5 artistes avec portrait, 6 spectacles,
9 événements, l'accroche réelle. Les migrations y sont à jour au 13 septembre 2026.

Le panneau de réglages est en bas de **chaque** page. Il pose un cookie : le
choix suit la navigation, on n'a pas à répéter le paramètre d'une page à l'autre.

| réglage | valeurs |
|---|---|
| `?fond=` | `plat` · `mesh` · `grain` |
| `?titre=` | `systeme` · `fraunces` · `playfair` · `instrument` · `bricolage` |

**Les trois pages du guide**, à garder ouvertes dans trois onglets :

- `/` — le hero, son titre en `clamp(2.2rem, 6vw, 3.6rem)` et l'accroche en dessous
- `/@camille-laurent/` — portrait, rôle public, dates, et depuis aujourd'hui la vidéo au clic
- `/spectacles/3/` — « Le Cri du homard », avec affiche et distribution

## Ce que la passe NE couvre PAS

Ces points ont un test qui tombe si on les casse ; y revenir à l'œil fait perdre
du temps :

- le contraste AA des **dix-huit** palettes, en clair et en sombre —
  `test_les_palettes_respectent_le_contraste_AA` mesure dix paires réellement
  peintes par palette ;
- le plan des titres (aucun niveau sauté) et, depuis le 13 septembre, le fait
  qu'un `h3` ne soit pas plus gros que le `h2` qui ouvre sa section ;
- le nom accessible de chaque champ, bouton et lien, et l'`alt` de chaque image ;
- l'absence de requête vers YouTube avant le clic du visiteur.

**La palette ne se choisit plus** : les dix-huit restent offertes au visiteur
(décision du 12 septembre). Ne pas rouvrir ce sujet ici — mais juger fond et
police sur la **palette 1**, celle que voit un visiteur sans cookie, puis vérifier
qu'on tient sur les deux extrêmes (2 sombre chaud, 17 vert néon/jaune acide).

## Ce qu'un détecteur externe en dit

`impeccable` (voir `docs/outils-agent.md`) a un avis sur les deux moitiés :

- le fond crème `#ece5d8` lui paraît générique ;
- sur les cinq candidates, il juge **Fraunces** et **Instrument Serif**
  surexposées, et ne dit **rien** de Playfair Display ni de Bricolage Grotesque.

C'est un élément au dossier, pas un ordre. Il se trompe assez souvent par
ailleurs pour qu'on ne le suive pas les yeux fermés.

## Reste

### Avant de juger
- [ ] Les trois onglets sont ouverts et rendent sans erreur en palette 1
- [ ] Le panneau de réglages est visible en bas de page et le choix survit à un
      changement de page (cookie posé)
- [ ] Cache vidé puis `/` rechargée : noter si un changement de police se voit au
      chargement (`font-display: swap`), et sur quelle page il est le plus gênant

### Le fond — trois candidats
- [ ] `?fond=plat` : sur `/`, le titre du hero reste net et détaché du fond
- [ ] `?fond=mesh` : idem, et l'animation ne distrait pas de la lecture de l'accroche
- [ ] `?fond=grain` : idem, et le grain ne « salit » pas les photos de
      `/@camille-laurent/` ni l'affiche de `/spectacles/3/`
- [ ] Avec le réglage « réduire les animations » du panneau de confort, le mesh
      cesse de bouger — un fond animé qui ignore ce réglage est éliminé d'office
- [ ] Le fond retenu tient sur la palette 2 (sombre chaud) et sur la 17 (vert
      néon/jaune acide) : ce sont les deux extrêmes des dix-huit servies
- [ ] Sur un vrai téléphone à 375 px, le fond retenu ne coûte pas un temps de
      chargement visible sur `/`

### La police de titre — cinq candidates
- [ ] Chacune des cinq est vue sur les **trois** pages avant de comparer : une
      police qui va au hero peut échouer sur une liste de spectacles
- [ ] Sur `/`, l'accroche « le spectacle vivant, en pleine lumière. » reste lisible
      en petit : elle est en `0.62em` du titre, donc la plus fine de la page
- [ ] À 375 px, le titre de `/spectacles/2/` — « Nuit blanche à Villeurbanne » —
      ne dépasse pas trois lignes et ne casse pas de mot
- [ ] Le logo « L'Improliante » de l'en-tête suit la police de titre : il est
      regardé **comme un logo**, pas comme un titre, sur les cinq candidates
- [ ] `/spectacles/6/` (« Cabaret des curiosités », **sans affiche**) : le titre
      porte la page seul, sans laisser de bloc vide au-dessus
- [ ] Instrument Serif n'a qu'une graisse : vérifier qu'aucun titre ne paraît
      faussement gras (le CSS s'en garde, ça se regarde quand même)
- [ ] La police retenue rend correctement les accents et les ligatures françaises
      sur « créations », « Améliorations », « Théo Nguyen »

### Les deux ensemble
- [ ] Le couple retenu est regardé sur les trois pages **à la suite**, sans
      changer de réglage entre elles
- [ ] Une serif fine sur le mesh animé reste lisible — c'est la combinaison que
      la fiche VIT-3 signale comme la plus risquée
- [ ] Le couple retenu ne fait pas paraître les cartes d'agenda de `/agenda/`
      plus lourdes que le mois qui les groupe (leur taille a été corrigée le
      13 septembre : le mois est passé à 1.4rem)

### Typographie fine — deux cas ouverts
- [ ] Écran à rail (`/espace/` ou `/bureau/`), sous 920 px de large : le titre de
      section et les titres qu'il groupe font la même taille (`1.15rem` tous les
      deux). Décider si cette hiérarchie plate est acceptée ou si le `h2` monte
- [ ] Les étiquettes de groupe du rail (« Le site », « Mon espace », « Finances »)
      sont à `0.68rem` = 10,88 px. Décider si elles passent à `0.7rem` — le
      contraste, lui, a déjà été arbitré

### Ce que la séance doit laisser derrière elle
- [ ] Le fond retenu est nommé dans `pilotage/VIT-3.md`, avec la raison en une phrase
- [ ] La police retenue y est nommée de même
- [ ] Les combinaisons éliminées sont nommées elles aussi : sans ça, la question
      se rouvre dans trois mois et se rejuge de zéro
- [ ] Les deux cas de typographie fine ci-dessus sont tranchés, ou explicitement
      reportés avec leur raison
