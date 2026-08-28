---
chantier: GED-1
statut: interrompu
---

# GED-1 — explorateur de fichiers (v2)

**Arrêté sur** — déplacement d'un dossier dans l'arbre, avec réalignement de la
visibilité sur tout le sous-arbre, commit `3d4555a`, 28 août.

## Reste

### Arbitrages
- [x] Trancher le degré d'interactivité : rendu serveur avec navigation par dossier, ou composant client — le cahier §2 exclut la SPA lourde, un explorateur est le cas limite qui interroge cette règle
- [ ] Décider si le glisser-déposer d'un fichier est dans le périmètre, sachant qu'il impose un envoi asynchrone et sa gestion d'erreur
- [x] Décider si le déplacement d'un dossier dans l'arbre est offert, et ce qu'il advient des droits des documents qu'il contient

### Vérifications
- [ ] La navigation reste utilisable au clavier seul et annonce le dossier courant — règle 9 de CLAUDE.md, et c'est ce qu'un explorateur rate le plus souvent
- [ ] La liste des destinations reste compréhensible sur un arbre profond : l'indentation par niveau suffit à distinguer deux dossiers homonymes
- [x] Un document dont le membre n'a pas le droit n'apparaît pas dans l'arbre, et son URL directe rend 403 — règles 1 et 5

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le premier arbitrage est le vrai sujet. Un explorateur de fichiers est l'écran qui pousse
le plus fort vers le client lourd, et le cahier a tranché contre — pour la performance
mobile et l'accessibilité. Trancher ici, c'est décider jusqu'où la règle plie.

## La fiche avait vieilli (28 août)

Le point de départ écrit ici était **faux** : l'explorateur existe depuis le commit
`6b7f753` — arbre latéral à quatre branches (Perso, Partagé, Bureau, Association),
navigation par dossier, création, renommage, suppression, versions, panneau repliable sur
mobile. La v1 ne se contentait pas de listes.

Deux items s'en trouvaient déjà réglés. Le **degré d'interactivité** était tranché de
fait — rendu serveur — et rien ne justifiait de rouvrir la question : BUD-1 venait de
montrer qu'un écran riche tient en HTML/CSS. L'**anti-IDOR** était couvert par 35 tests
documentaires existants (« dossier privé invisible pour un autre membre », « invisible du
bureau »).

Restait un vrai manque, et un seul : **le déplacement**. Sans lui, un dossier mal rangé
l'est pour de bon — ou il faut le recréer et tout re-téléverser.

L'arbitrage sur les droits est tranché ainsi : la visibilité se réaligne sur le dossier
d'accueil **et se propage à tout le sous-arbre**. L'alternative — garder un dossier
« privé » vivant dans une branche partagée — donnait un mensonge affiché à l'écran.
La conséquence étant lourde, elle est annoncée avant le geste, avec le nombre de
sous-dossiers emportés.

Le piège technique mérite d'être retenu : avec `node_order_by`, treebeard **renumérote
les chemins matérialisés à chaque création**. Une instance obtenue avant une création
voisine porte un `path` périmé, et `move` ne déplace alors rien — sans erreur. Seuls les
tests l'ont montré ; la relecture ne le montrait pas.

**Reste ouvert** : le glisser-déposer, écarté faute d'être indispensable (il impose un
envoi asynchrone et sa gestion d'erreur, quand le déplacement par formulaire lève déjà
l'impasse). Et la vérification clavier, qui appartient à une passe de QA.
