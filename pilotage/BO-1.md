---
chantier: BO-1
statut: à venir
---

# BO-1 — relances automatiques (v2)

**Point de départ** — Rien n'est commencé. Les données nécessaires existent pourtant déjà :
`Adhesion` porte ses dates et son `montant_verse` (`apps/budget/`), `Facture` porte son
état et son échéance (`apps/facturation/`). Il manque le déclencheur, l'envoi, et la trace
de ce qui a été relancé.

## Reste

### Arbitrages
- [ ] Trancher le déclencheur : commande `manage.py` en cron sur le VPS, ou tâche applicative — le VPS n'a pas encore de broker, et en ajouter un pour ça seul est une décision d'infrastructure (dépend de DEP-1)
- [ ] Fixer le calendrier de relance des adhésions en retard (combien d'envois, à quel intervalle, jusqu'à quand) et le faire entrer dans les paramètres éditables en admin — règle 8 de CLAUDE.md, jamais en dur
- [ ] Décider si une facture relancée le reste après paiement partiel, et ce que devient la relance sur un avoir

### Vérifications
- [ ] Une relance envoyée laisse une trace horodatée sur l'objet relancé, de sorte qu'un second passage du cron ne la renvoie pas
- [ ] Un membre à jour de cotisation ne reçoit jamais de relance — vérifié sur un jeu couvrant la veille et le lendemain de l'échéance

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le premier arbitrage dépend du déploiement : choisir le mode de déclenchement sans savoir
ce que le VPS fait tourner reviendrait à décider à l'aveugle. DEP-1 le débloque.

La logique de sélection des retards va dans un `services.py`, pas dans une commande — la
commande orchestre et journalise. C'est la convention du dépôt, et elle rend la règle
testable sans cron.
