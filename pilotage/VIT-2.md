---
chantier: VIT-2
statut: clos
---

# VIT-2 — billetterie et inscription aux spectacles (v3)

**Arrêté sur** — feuille d'inscription gratuite du public : jauge sur l'`Evenement`,
réservation sous verrou, consultation par jeton, purge RGPD, commit `2ac40ff`, 28 août.

## Reste

### Arbitrages
- [x] Trancher inscription libre ou billetterie payante — la seconde fait entrer un prestataire de paiement, une obligation comptable et un rapprochement avec le module budget ; ce sont deux chantiers différents sous un même mot
- [x] Décider si la jauge se pose sur l'`Evenement` ou sur une occurrence, sachant que le modèle actuel ne distingue pas les deux
- [x] Décider du sort des données de réservation après le spectacle (durée de conservation, RGPD)

### Vérifications
- [x] Deux réservations simultanées sur la dernière place n'en laissent passer qu'une — vérifié sous concurrence réelle, pas en séquentiel
- [x] Une réservation confirmée reste consultable par son porteur sans compte, par un lien qu'aucun autre ne peut deviner

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

## Ce qui a été fait, et ce qui ne l'a pas été (28 août)

**Inscription gratuite, pas billetterie.** Le premier arbitrage séparait deux chantiers
sous un même mot ; c'est le petit qui est livré. Aucun prestataire de paiement, aucune
obligation comptable, aucune donnée bancaire. **La billetterie payante reste entière** —
elle mériterait sa propre fiche le jour où elle sera demandée, et rien de ce qui est
livré ici ne la gêne : une jauge et des réservations lui serviraient de socle.

Les deux autres arbitrages se sont tranchés par le modèle plutôt que par une décision.
La **jauge va sur l'`Evenement`** parce que le cahier §6 fait déjà de la représentation
un événement de l'agenda : il n'existe pas d'autre occurrence où la poser. La
**conservation RGPD** prend la forme d'une commande de purge à 90 jours, calée sur la
date de l'événement et non sur celle de la réservation — une place prise un an à l'avance
ne doit pas s'effacer avant la soirée. Elle est manuelle exprès : la planifier suppose un
cron, donc DEP-1.

La vérification qui comptait est **faite pour de bon**. La dernière place ne se teste pas
en séquentiel : huit demandes concurrentes sur une seule place, derrière une barrière, et
le verrou vérifié par mutation — retiré, le test rend « 8 réservations acceptées pour
1 place » ; remis, une seule passe. C'est l'outillage PostgreSQL monté le même jour qui
a rendu cette preuve possible.

Deux manques ont failli passer, et ils auraient vidé la fonction de son sens : la jauge
n'était réglable que depuis l'admin Django (`places_max` manquait au formulaire du
bureau), et rien n'affichait les inscrits — on aurait collecté des noms que personne ne
lit. Les deux sont là.

**Reste ouvert, hors de cette fiche** : l'envoi d'un e-mail de confirmation au moment de
la réservation. Le porteur repart avec son lien à l'écran, mais rien ne le lui envoie —
et l'envoi d'e-mail bute sur le même mur que VIT-1, celui d'une IP neuve qui expédie en
indésirable. À reprendre avec le déploiement.
