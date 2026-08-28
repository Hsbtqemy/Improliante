---
chantier: FAC-1
statut: interrompu
---

# FAC-1 — éditeur de facture (v2)

**Arrêté sur** — duplication d'une pièce en brouillon et déplacement des lignes par
boutons ▲▼, commit `b4302e8`, 28 août.

## Reste

### Vérifications à l'œil
- [ ] Les boutons ▲▼ déplacent bien la ligne dans l'éditeur, et l'ordre enregistré correspond à ce que l'écran montrait — le comportement JS n'est couvert par aucun test automatique
- [ ] Au clavier seul, monter puis descendre une ligne reste suivable : le focus accompagne le contenu déplacé

### Arbitrages
- [x] Trancher ce que l'éditeur apporte que le formset ne fait pas — recalcul en direct, réordonnancement des lignes, duplication d'une facture ? Sans cette liste, le chantier n'a pas de fin
- [x] Décider si le total se calcule côté client pour l'affichage, étant entendu que le serveur reste seul juge à l'enregistrement

### Vérifications
- [x] Une facture validée reste inéditable par l'éditeur : la correction passe par un avoir, jamais par une retouche — règle 4 de CLAUDE.md
- [x] La numérotation reste attribuée à la validation et sans trou, quel que soit le chemin de saisie — vérifié par la suite test-first existante, qui doit rester verte

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

C'est le ticket où le risque est le plus asymétrique : le gain est du confort, et la zone
touchée est la numérotation légale — séquentielle, continue, attribuée à la validation.
La contrainte n'est pas négociable et la suite de tests qui la tient est test-first. Un
éditeur qui la contournerait, même par mégarde, coûterait plus qu'il ne rapporte.

## La fiche était largement dépassée (28 août)

« Rien n'est commencé » était faux, et de loin. `front/static/js/facturation.js` fait déjà
l'ajout dynamique de lignes, la suppression par ligne et le **total HT/TVA/TTC recalculé à
la saisie** — soit le « recalcul en direct » que le premier arbitrage citait comme à
trancher. Le second arbitrage décrivait ce qui était déjà en place : calcul client pour
l'affichage, serveur seul juge à l'enregistrement. Et les deux vérifications étaient
couvertes — `test_facture_validee_non_editable` d'un côté, la suite test-first de la
numérotation de l'autre, renforcée le même jour par un test de concurrence sur PostgreSQL.

De la liste que l'arbitrage 1 demandait d'établir, deux gestes manquaient vraiment.

La **duplication** est livrée, et son intérêt tient à ce qu'elle NE copie pas : ni numéro,
ni statut, ni date d'émission, ni lien d'avoir. Reprendre le numéro d'origine créerait un
doublon dans une série qui doit rester unique et continue (règle 4).

Le **déplacement de ligne** s'est révélé aux trois quarts fait : `_renumeroter_lignes`
attribuait déjà l'ordre d'après la position d'affichage. J'avais supposé le contraire — que
le champ `ordre` restait à zéro faute d'être exposé au formset — et le code m'a détrompé.
Il ne manquait que le moyen de bouger une ligne. Les boutons échangent les **valeurs**
entre lignes voisines et non les `<tr>` : les noms de champs d'un formset portent leur
index, donc permuter les lignes dans le DOM ne changerait rien à ce que le serveur reçoit.

**Reste ouvert** : le comportement des boutons n'est couvert par aucun test — il demande
un navigateur. L'invariant serveur dont ils dépendent l'est. D'où les deux cases à l'œil
ci-dessus, qui sont tout ce qui empêche de clore la fiche.
