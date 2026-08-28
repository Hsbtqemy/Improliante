---
chantier: GED-1
statut: à venir
---

# GED-1 — explorateur de fichiers (v2)

**Point de départ** — Rien n'est commencé côté interface. Le socle est là : `Dossier` est
un arbre treebeard, `Document` porte ses versions (`apps/documents/services.py`), et le
dépôt comme la consultation contrôlée existent depuis le back-office. Ce qui manque est
une interface de navigation, là où la v1 se contente de listes.

## Reste

### Arbitrages
- [ ] Trancher le degré d'interactivité : rendu serveur avec navigation par dossier, ou composant client — le cahier §2 exclut la SPA lourde, un explorateur est le cas limite qui interroge cette règle
- [ ] Décider si le glisser-déposer d'un fichier est dans le périmètre, sachant qu'il impose un envoi asynchrone et sa gestion d'erreur
- [ ] Décider si le déplacement d'un dossier dans l'arbre est offert, et ce qu'il advient des droits des documents qu'il contient

### Vérifications
- [ ] La navigation reste utilisable au clavier seul et annonce le dossier courant — règle 9 de CLAUDE.md, et c'est ce qu'un explorateur rate le plus souvent
- [ ] Un document dont le membre n'a pas le droit n'apparaît pas dans l'arbre, et son URL directe rend 403 — règles 1 et 5

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Le premier arbitrage est le vrai sujet. Un explorateur de fichiers est l'écran qui pousse
le plus fort vers le client lourd, et le cahier a tranché contre — pour la performance
mobile et l'accessibilité. Trancher ici, c'est décider jusqu'où la règle plie.
