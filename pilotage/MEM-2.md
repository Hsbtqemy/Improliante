---
chantier: MEM-2
statut: à venir
---

# MEM-2 — gestion des bénévoles et plannings (v3)

**Point de départ** — Rien n'est commencé. Une piste voisine est déjà notée au cahier §6
(« appel à bénévoles » autour des projets en création), sans modèle ni écran. Le refactor
de juillet aide : `Membre` est une personne, le compte de connexion est optionnel — un
bénévole sans compte est donc représentable tel quel.

## Reste

### Arbitrages
- [ ] Trancher si un bénévole est un `Membre` sans adhésion ou une entité distincte — le refactor « Membre = personne, compte optionnel » rend la première option viable, la seconde duplique l'annuaire
- [ ] Décider si le planning se pose sur l'`Evenement` existant ou sur un créneau propre, un événement pouvant demander plusieurs postes à des heures différentes
- [ ] Décider qui inscrit qui : le bénévole se positionne, ou le bureau affecte

### Vérifications
- [ ] Un bénévole sans compte de connexion peut être inscrit à un créneau et figurer au planning — c'est ce que le modèle actuel doit déjà permettre
- [ ] Un bénévole ne voit que ses propres créneaux depuis l'espace membre, jamais ceux d'un autre par un identifiant d'URL — règle 1 de CLAUDE.md

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le premier arbitrage est celui qui coûte le plus cher à reprendre : il décide si
l'annuaire reste unique. Le commit `623ef62` a précisément séparé la personne du compte
de connexion pour garder cette porte ouverte — la refermer en créant une entité parallèle
serait défaire ce travail sans le dire.
