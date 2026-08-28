---
chantier: VIT-1
statut: à venir
---

# VIT-1 — newsletter et envoi groupé (v3)

**Point de départ** — Rien n'est commencé, et rien dans le modèle ne le prépare : il
n'existe aujourd'hui aucune notion d'abonnement ni de consentement à recevoir. Le
formulaire de contact porte un consentement RGPD, mais il vaut pour ce message-là.

## Reste

### Arbitrages
- [ ] Trancher l'hébergement de l'envoi : service tiers ou envoi depuis le VPS — un envoi groupé depuis une IP neuve arrive en indésirable, c'est le vrai coût de la seconde option (dépend de DEP-1)
- [ ] Décider du recueil de consentement : opt-in explicite au moment de l'adhésion, ou inscription séparée depuis le site — le premier lie l'abonnement à l'adhésion, le second ne le fait pas
- [ ] Décider si les membres et le public reçoivent la même lettre

### Vérifications
- [ ] Chaque envoi porte un lien de désinscription qui fonctionne sans connexion, et la désinscription est effective au premier envoi suivant
- [ ] Un membre désabonné cesse de recevoir la lettre sans perdre les convocations statutaires, qui ne sont pas de la newsletter

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le dernier item est la distinction qui compte : une convocation à une assemblée générale
est une obligation statutaire, pas une communication à laquelle on s'abonne. Les confondre
dans le même mécanisme de désinscription ferait rater une convocation à un membre qui a
seulement voulu quitter la lettre d'information.
