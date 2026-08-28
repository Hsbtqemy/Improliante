# Gabarits `pilotage/`

Deux natures, à ne pas mélanger.

- **Le chantier** (`pilotage/<CODE>.md`) porte un **état** : ce qui reste à faire. On
  coche une fois, l'item disparaît.
- **La passe de QA** (`pilotage/qa/<nom>.md`) porte une **procédure rejouable** : on la
  relance à chaque fois qu'on veut revérifier. On la décoche et on recommence.

Un ticket de backlog n'est pas une troisième nature : c'est un chantier dont le travail
n'a pas commencé — `statut: à venir`. Une idée devient un ticket, puis un chantier, puis
un chantier clos, **sans jamais changer de document**.

> Ce fichier DÉCRIT le contrat ; `journal-contrat.mjs` le DÉFINIT. Quand les deux
> divergent, c'est le code qui a raison — c'est déjà arrivé.

---

## Gabarit 1 — le chantier

Un fichier par chantier, nommé d'après son code : `pilotage/R6.md`.

```markdown
---
chantier: R6
statut: interrompu
audit: docs/AUDIT_2026-06-28.md
---

# R6 — paragraphes manuels

**Arrêté sur** — geste ¶ par-segment (matrice + Tours), commit `be36385`, 23 juillet.

## Reste

### Arbitrages
- [ ] Trancher le sort du microscope optionnel

### Vérifications
- [ ] Vérifier la propagation ¶ sur les segments hérités (D-P10)
- [x] Bump engine + shell 0.3.3 → 0.4.0

## Contexte

Prose libre. Ce que je me raconterai dans trois semaines. Rien ici n'est lu par
l'outil — écris ce que tu veux, aussi long que nécessaire.

Collision connue : R5 partage 25 fichiers, dont sidecar.py.
```

| Élément | Règle | Si absent |
|---|---|---|
| `chantier:` | Le code, **tel qu'il apparaît dans les sujets de commit** | Le nom de fichier sert de code |
| `statut:` | `à venir` · `interrompu` · `différé` · `clos` · `livré` · `abandonné` | Traité comme `interrompu` |
| `audit:` | Chemin du document qui porte le tableau des constats | Pas de remontée, pas de lien |
| `# Titre` | Premier H1 | Le code sert de titre |
| `**Arrêté sur**` | Le **paragraphe** entier après le tiret — les lignes repliées sont recollées, comme celles d'une case ; l'outil le signale **décalé** dès qu'il ne cite plus le dernier commit de code. `**Point de départ**` est accepté à sa place, et c'est le mot juste sur un `à venir` — qui n'est jamais signalé décalé, n'ayant aucun commit à citer. L'écran affiche le libellé que la fiche a écrit, pas celui que son statut suggère | Ligne omise |
| `## Reste` | Les cases ; les `###` y regroupent par zone, comme dans une passe | Section absente de l'écran |
| `## Contexte` | Prose, affichée telle quelle | Rien |

**`statut: abandonné`** est pour ce qu'on a décidé de NE PAS faire. Fermé, mais pas
fait — et c'est la différence avec `clos`. Sans le mot, on supprime le fichier et le
raisonnement part avec lui ; la fiche abandonnée garde son `Reste` ouvert **exprès**,
comme trace de ce à quoi on a renoncé. Le contrôleur ne réclame donc pas d'`audit:`
dessus, et l'écran le range avec les fermés sans jamais le dire « livré ».

**`statut: livré`** est le seul qui parle d'**intégration**, et l'outil la mesure : si le
dernier commit du chantier ne vit sur aucune ref d'intégration, la fiche est **démentie**
et l'écran l'annonce « hors de <refs> ». Déclarer reste utile — le journal se charge de
contredire.

**`statut: à venir`** est pour la fiche écrite *avant* le premier commit de code : le
chantier est cadré, il n'a pas commencé. Sans lui, un chantier neuf s'annonce
`interrompu` — le mot dit qu'on s'est arrêté en plein travail alors qu'on n'a rien
commencé.

Rien n'oblige à le tenir à jour : le journal le **dément** tout seul dès qu'un commit
citant le code touche autre chose que `pilotage/` et le dossier de documentation. La
fiche affiche alors « N commits de code », et le tableau de bord compte les « à venir »
démentis, comme il compte les points de reprise décalés.

**`statut: différé`** est pour le chantier mis en attente *exprès*, parce qu'autre chose
doit aboutir d'abord — un constat d'audit repoussé derrière la vérification d'un geste,
une décision qui attend qu'un morceau soit fini pour se trancher au mieux. `interrompu`
dit qu'on s'est arrêté en plein travail ; `différé` dit qu'on a choisi d'attendre. Les
deux comptent comme ouverts et n'ont pas la même dette.

Contrairement à `à venir`, il n'est **pas** démenti mécaniquement. Le compte de commits
de code porte sur toute la fenêtre et ne sait pas ce qui précède la mise en attente : un
démenti se déclencherait sur l'historique légitime d'avant. Il faudrait une date de mise
en attente, que la fiche ne porte pas — à écrire dans `## Contexte` en attendant.

> Ce démenti a besoin de savoir où vit ta documentation. Sans `documentation.dossier`
> dans l'inventaire, une note de conception compte comme du code et dément un `à venir`
> qui était juste.

Les passes ne se déclarent pas ici : c'est la passe qui nomme son chantier, pas
l'inverse. Une section `## QA` qui les listerait ne serait jamais lue.

---

## Gabarit 2 — la passe de QA

Un fichier par passe, dans `pilotage/qa/`.

```markdown
---
passe: Paragraphes manuels
chantier: R6
duree: 8 min
derniere: 2026-08-17
---

# QA — geste ¶ par-segment

Contexte de la passe, ce qu'elle couvre, ce qu'elle ne couvre pas. Prose libre.

### Matrice

- [ ] Le geste ¶ apparaît au survol d'un segment, pas au clic
- [ ] Un ¶ posé survit à un changement d'onglet

### Responsive

- [ ] Sur 375 px, la barre de segment ne masque pas le geste
```

| Élément | Règle | Si absent |
|---|---|---|
| `passe:` | Nom affiché | Le nom de fichier sert de nom |
| `chantier:` | Un code, ou `—` pour une passe transversale | Traitée comme transversale |
| `duree:` | Indicatif, affiché tel quel | Non affiché |
| `derniere:` | Date de la dernière réinitialisation ; l'outil en tire l'âge de la passe | Non affiché |
| `### Zone` | Regroupe les cases qui suivent | Cases regroupées sous « Général » |

**Les H3 sont le seul niveau de regroupement.** Une zone, un écran, un thème — un seul
niveau, et par titre plutôt que par indentation. Une sous-liste indentée est ambiguë :
cocher le parent coche-t-il les enfants ? Un titre ne pose pas la question.

Une case doit être **une affirmation vérifiable**, avec son attendu. « Croiser une
portée vide » ne dit pas ce qui doit se passer ; on coche ce qu'on voit.

---

## Rejouer une passe

1. Cocher au fur et à mesure ; la page réécrit le markdown.
2. Commiter le résultat — **la passe est archivée**, le commit porte la date et le score.
3. Passe suivante : le bouton *réinitialiser* décoche tout et met à jour `derniere:`.

L'historique des passes est donc `git log -- pilotage/qa/<nom>.md`. Rien à archiver à la
main, et le gabarit n'est jamais détruit puisqu'il se régénère à chaque réinitialisation.

---

## Quatre règles strictes

1. Les noms de section sont exactement `## Reste`, `## Contexte`, et les H3 de zone.
   Pas de variante, pas d'emoji, pas de compteur dans le titre.
2. Les cases n'existent que sous `## Reste` (chantier) et sous un H3 (passe). Ailleurs,
   elles ne sont ni comptées ni cochables — donc invisibles.
3. Une case = une ligne = une affirmation vérifiable. Pas d'indentation. Une case peut
   se continuer sur les lignes suivantes indentées ; elles sont recollées à la première.
4. Tout le reste est libre et ne sera jamais interprété.
