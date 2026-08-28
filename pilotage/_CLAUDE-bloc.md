Bloc à coller dans le `CLAUDE.md` (ou `AGENTS.md`) du dépôt hôte. Le préfixe `_` le
rend invisible pour l'outil : ce n'est ni un chantier ni une passe.

---

## Pilotage

Un chantier interrompu a un fichier `pilotage/<CODE>.md`. Une QA visuelle est une
passe rejouable dans `pilotage/qa/<nom>.md`. Voir `pilotage/_TEMPLATE.md`.

IMPORTANT — respecter exactement `## Reste` et les H3 de zone : l'outil ne lit que
ces sections.

- Fin de session : mettre à jour le `Reste` du chantier travaillé.
- `statut:` se prend dans `à venir` · `interrompu` · `différé` · `clos` · `livré` ·
  `abandonné`,
  et rien d'autre — le contrôleur refuse le reste. `différé` = mis en attente exprès
  (autre chose doit aboutir d'abord), à distinguer d'`interrompu` = arrêté en plein
  travail. `abandonné` = décidé de ne pas le faire : fermé mais pas fait, et la fiche
  garde son `Reste` ouvert exprès plutôt que d'être supprimée avec son raisonnement.
  `livré` est démenti par l'écran si le dernier commit n'est sur aucune ref d'intégration.
- Le commit de code d'abord, le commit de fiche ensuite, **séparément** : une fiche
  ne peut pas citer le commit qui la met à jour, et les commits qui ne touchent que
  `pilotage/` sont exclus du datage.
- **Le commit de code doit CITER le code du chantier**, dans son sujet ou son corps.
  Un chantier n'est daté que par les commits qui le citent ET qui touchent autre chose
  que `pilotage/` — les deux à la fois. Sans citation, la fiche affiche `0 commit`,
  aucune date, aucune barre sur la fresque, quel que soit le travail fait.
- Avant de clore une session : `pilote verifier` (code de retour non nul
  = l'outil lira mal le dossier ; `--strict` rend les avertissements bloquants).
- QA visuelle : écrire une passe dans `pilotage/qa/`, jamais dans le fil de
  conversation. Regrouper les points par zone en H3.
- Ne jamais cocher soi-même une case d'une passe de QA.
- Ne pas créer de fichier pour un finding traité en un seul commit.

Le journal se lit avec `pilote` puis `localhost:4123` — la commande est idempotente,
se retaper sans vérifier si un serveur tourne est le geste prévu (`pilote arreter` ferme,
`pilote aide` liste tout) (git + `pilotage/`, lecture
seule sauf les cases, dont l'écriture est bornée à `pilotage/`).
