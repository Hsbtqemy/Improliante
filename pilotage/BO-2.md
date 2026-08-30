---
chantier: BO-2
statut: interrompu
---

# BO-2 — les réglages du bureau : quatre écrans et les signataires

**Arrêté sur** — l'écran unique « Paramètres de l'association » éclaté en quatre
(Identité légale, Textes du site, Page Contact, Signataires), et le signataire devenu
un objet géré depuis le bureau au lieu de deux champs texte, commit `c123942`,
29 août 2026. 507 tests verts, `ruff` propre, `manage.py check` sans remarque.

## Reste

### Mise au dépôt
- [x] Les réglages et les signataires partent dans un commit qui cite `BO-2` dans son sujet — sans citation, la fiche reste à « 0 commit », sans date et sans barre sur la fresque, quel que soit le travail fait
- [x] Ce commit est **séparé** de celui du slug membre et de celui du rapatriement des reçus : ces deux-là ne touchent pas aux réglages, tiennent chacun en un commit et n'ont donc pas de fiche — les mêler daterait `BO-2` d'un travail qui n'est pas le sien
- [x] `pytest` passe sur un checkout neuf de `main` — 507 passés, 3 ignorés au commit `c123942`, mesuré dans un arbre détaché ; `main` en portait 10 en échec avant le découpage
- [x] **Chaque** commit de la salve passe, pas seulement le dernier : mesuré un à un dans un arbre détaché, de `c7a05ce` à la fiche — `git bisect` est exploitable de bout en bout
- [x] `main` est poussé sur `origin` : sans intégration, `BO-2` ne pourrait pas passer `livré` sans être démenti à l'écran

### Vérifications à l'œil
- [ ] Sur 375 px, les quatre onglets de réglages restent tous atteignables — l'écran d'avant n'en portait aucun, cette barre n'a jamais été vue à cette largeur
- [ ] Une signature téléversée s'imprime à la bonne taille sur les trois gabarits, devis, facture et cerfa — les tests vérifient que le bloc est là ou absent, jamais ses proportions
- [ ] Une signature photographiée au téléphone, donc lourde, ne fait pas gonfler le PDF au-delà de quelques centaines de ko — l'image est embarquée en data-URI dans le document, son poids est celui du fichier téléversé

### Arbitrages
- [ ] Décider si l'écran montre la signature téléversée : aujourd'hui le bureau ne peut vérifier qu'elle est droite et lisible qu'en produisant un PDF, l'image ne s'affichant nulle part — elle est en stockage privé (règle 5), un aperçu demande donc une vue authentifiée dédiée, pas une balise `<img>` sur `.url`
- [ ] Trancher le sort du signataire par défaut retiré du service : il quitte le sélecteur, et le prochain enregistrement de l'écran l'efface **sans le dire** — soit on annonce l'effacement, soit on refuse le retrait tant qu'il est le défaut
- [ ] Décider si la conversion portée par la migration `0014` mérite un test : elle reprend `signataire_nom` en un vrai `Signataire` et ne s'exécutera qu'une fois, sur une base qui n'existe pas encore (dépend de DEP-1) — sans test elle s'exécute en aveugle le jour du déploiement, et c'est le seul jour où elle sert

## Contexte

**Pourquoi quatre écrans pour un seul objet.** `ParametresAssociation` est un singleton,
et il le reste : ce sont les *écrans* qui se séparent, parce qu'ils ne servent pas le même
public. L'identité légale (RNA, SIRET, article du CGI, IBAN) s'imprime en tête des reçus
fiscaux et des factures et se remplit une fois pour toutes ; les textes du site changent
au gré des saisons ; la page Contact est de l'exploitation courante. Les trois étaient
empilés dans un formulaire unique de quinze champs où rien n'indiquait ce qui partait au
fisc et ce qui partait au visiteur.

D'où `update_fields` dans `_page_reglages` : chaque écran n'écrit **que** ses propres
colonnes. Un `save()` complet recopierait l'objet entier, et l'enregistrement d'une page
écraserait au passage ce qu'une autre vient de changer — panne invisible et pénible à
comprendre quand deux personnes du bureau travaillent en même temps. Un test la tient
(`test_un_ecran_de_reglages_n_ecrit_que_ses_propres_champs`).

**Le signataire.** `signataire_nom` et `signataire_qualite` étaient deux champs texte, sans
image ni mention de délégation, et ne servaient que de repli sur le Cerfa — alors que le
modèle `Signataire` existait déjà à côté, avec tout cela. Deux mécanismes pour une même
chose, dont un dégradé. La migration `0014` convertit le texte en un vrai `Signataire`,
le promeut défaut, puis retire les colonnes ; l'ordre des opérations compte, les colonnes
doivent encore exister au moment d'être lues.

Le défaut est **présélectionné** à la création d'une pièce, jamais appliqué au rendu : ce
qu'on voit à l'écran est ce qui s'imprime, et changer le défaut ne réécrit pas une pièce
déjà saisie. Sur une pièce existante, la présélection ne joue pas — elle réécrirait un
choix déjà fait, ou en poserait un là où l'absence de signataire était voulue.

La suppression d'un signataire est **refusée** dès qu'une pièce le porte : les clés
étrangères sont en `SET_NULL`, supprimer effacerait le nom sans bruit sur des devis, des
factures et des reçus déjà établis. Le geste offert est le retrait du service
(`actif = False`), qui le sort des choix sans toucher au passé. C'est aussi ce qui rend
l'écran capable d'afficher, en face de chaque nom, le nombre de pièces qui le portent.

**Ce que ce chantier ne couvre pas**, bien que ce soit dans le même arbre de travail : la
fiche publique du membre passée à `/@prenom-nom` (migration `0013`, redirection 301 de
l'ancienne `/membres/<id>/`, sitemap et JSON-LD suivis), et les reçus fiscaux rapatriés
dans « Mes fichiers » avec l'ancienne page réduite à une redirection (plus l'aide sur le
champ URL des liens réseaux, migration `0012`). Chacun tient en un commit : pas de fiche,
conformément à la règle. Ils sont cités ici uniquement parce que leur commit doit être
séparé de celui-ci.

**Collision avec DEP-1.** L'image de signature vit dans `media_prive`. La case de DEP-1
qui exige que l'archive contienne `media` **et** `media_prive` couvre désormais aussi les
signatures : sans elle, un déploiement perdrait les signatures avec les factures.

**Le découpage.** L'arbre de travail portait quatre sujets mêlés ; il est parti en quatre
commits, dans l'ordre imposé par les migrations (`0012` → `0013` → `0014`) : l'aide sur
l'adresse d'un profil réseau, l'adresse `/@prenom-nom`, les reçus rapatriés, puis
celui-ci. Seul le dernier cite `BO-2` — les trois autres tiennent chacun en un commit et
n'ont pas de fiche.

**La réparation de l'amont.** Le découpage a mis au jour une tranche rouge qui ne venait
pas de lui : `e19afbb` avait emporté par mégarde les tests de `Membre.slug`, dont rien
n'implémentait le modèle, et `a34343a` avait laissé deux gabarits de côté au motif qu'ils
portaient du travail non commité — dont le test que ce commit installait lui-même. Neuf
commits étaient rouges, de `e19afbb` à la fiche. Les deux commits ont été refaits : le
premier rendu à son sujet (les tests de slug rejoignent le commit du slug), le second
complété des deux gabarits. Le reliquat « Gestion » que j'avais d'abord commis à part
disparaît, absorbé par le commit qui aurait dû le porter. L'arbre final est resté
identique au bit près, vérifié par `git diff` entre l'ancien commit de `BO-2` et le
nouveau.
