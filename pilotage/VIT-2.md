---
chantier: VIT-2
statut: à venir
---

# VIT-2 — billetterie et inscription aux spectacles (v3)

**Point de départ** — Rien n'est commencé. L'agenda public expose les événements et leur
export iCal ; aucun modèle ne porte de place, de jauge ni de réservation.

## Reste

### Arbitrages
- [ ] Trancher inscription libre ou billetterie payante — la seconde fait entrer un prestataire de paiement, une obligation comptable et un rapprochement avec le module budget ; ce sont deux chantiers différents sous un même mot
- [ ] Décider si la jauge se pose sur l'`Evenement` ou sur une occurrence, sachant que le modèle actuel ne distingue pas les deux
- [ ] Décider du sort des données de réservation après le spectacle (durée de conservation, RGPD)

### Vérifications
- [ ] Deux réservations simultanées sur la dernière place n'en laissent passer qu'une — vérifié sous concurrence réelle, pas en séquentiel
- [ ] Une réservation confirmée reste consultable par son porteur sans compte, par un lien qu'aucun autre ne peut deviner

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le premier arbitrage sépare deux chantiers de tailles très différentes : une feuille
d'inscription tient en un modèle et deux vues ; une billetterie payante engage un
prestataire, la comptabilité et la conservation de données de paiement. Le cahier §15 les
écrit sur la même ligne — c'est à l'usage de trancher.

Le premier item de vérification est la seule vraie difficulté technique du ticket, et il
ne se teste pas en cliquant : la dernière place est exactement l'endroit où une jauge
naïve laisse passer deux réservations.
