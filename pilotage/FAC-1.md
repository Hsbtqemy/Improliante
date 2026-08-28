---
chantier: FAC-1
statut: à venir
---

# FAC-1 — éditeur de facture (v2)

**Point de départ** — Rien n'est commencé. Les formulaires v1 tiennent le besoin : lignes
multiples par formset, client à la volée, brouillon puis validation, PDF WeasyPrint, avoir
sur facture validée. L'éditeur v2 vise le confort de saisie, pas une capacité manquante.

## Reste

### Arbitrages
- [ ] Trancher ce que l'éditeur apporte que le formset ne fait pas — recalcul en direct, réordonnancement des lignes, duplication d'une facture ? Sans cette liste, le chantier n'a pas de fin
- [ ] Décider si le total se calcule côté client pour l'affichage, étant entendu que le serveur reste seul juge à l'enregistrement

### Vérifications
- [ ] Une facture validée reste inéditable par l'éditeur : la correction passe par un avoir, jamais par une retouche — règle 4 de CLAUDE.md
- [ ] La numérotation reste attribuée à la validation et sans trou, quel que soit le chemin de saisie — vérifié par la suite test-first existante, qui doit rester verte

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

C'est le ticket où le risque est le plus asymétrique : le gain est du confort, et la zone
touchée est la numérotation légale — séquentielle, continue, attribuée à la validation.
La contrainte n'est pas négociable et la suite de tests qui la tient est test-first. Un
éditeur qui la contournerait, même par mégarde, coûterait plus qu'il ne rapporte.
