// Inventaire du dépôt pour `pilote`. Facultatif : sans lui on garde les fiches, les
// passes, le contrôleur et le front d'intégration ; on perd les masses par aire, la
// veille à seuil et les liens code → document.
//
// Il ne porte QUE ce qu'aucun outil ne peut deviner. Aucune grammaire, aucun réglage
// de lecture — ceux-là vivent dans `journal-contrat.mjs`, côté outil.

export default {
  // De l'amont vers l'aval. Ce dépôt n'a qu'une branche d'intégration : un chantier
  // `livré` dont le dernier commit ne vit pas sur `origin/main` sera démenti à l'écran.
  refs: ["origin/main"],

  // Un préfixe de chemin par entrée, le PREMIER qui matche l'emporte — d'où l'ordre :
  // les chemins longs avant les courts. Plusieurs préfixes peuvent porter le même nom
  // d'aire : leurs masses s'additionnent en une seule série.
  aires: [
    ["vitrine",      "apps/vitrine/"],
    ["espace membre", "apps/espace_membre/"],
    ["backoffice",   "apps/backoffice/"],
    ["finances",     "apps/facturation/"],
    ["finances",     "apps/budget/"],
    ["gouvernance",  "apps/gouvernance/"],
    ["GED",          "apps/documents/"],
    ["GED",          "apps/medias/"],
    ["contenus",     "apps/spectacles/"],
    ["contenus",     "apps/agenda/"],
    ["noyau",        "apps/coeur/"],
    ["noyau",        "apps/common/"],
    ["front",        "front/"],
    ["config",       "config/"],
    ["déploiement",  "deploiement/"],
    ["docs",         "docs/"],
    // Un préfixe peut désigner un FICHIER : `aire()` teste `p === pre` avant
    // `startsWith`. Sans ces entrées, dix fichiers suivis ne pesaient dans aucune aire
    // — mesuré à la mise en place, dont `CLAUDE.md` (225 lignes) et `requirements.txt`.
    // Plusieurs préfixes portant le même nom s'additionnent en une seule série.
    ["docs",         "CLAUDE.md"],
    ["docs",         "README.md"],
    ["outillage",    "manage.py"],
    ["outillage",    "requirements.txt"],
    ["outillage",    "pytest.ini"],
    ["outillage",    "ruff.toml"],
    ["outillage",    ".env.example"],
    // PAS de fourre-tout `["racine", ""]` en dernier : il attraperait `pilotage/`, et
    // l'aire grossirait à chaque fiche écrite. La tenue du journal n'est pas du code.
  ],

  // Sert à distinguer un commit de cadrage (note + fiche) d'un commit de code : sans
  // le dossier, une note de conception compterait comme du code et démentirait un
  // `statut: à venir` qui était juste.
  //
  // `sources` reste vide tant qu'aucun document de `docs/` ne porte de code de
  // chantier — le déclarer ne rendrait qu'une table vide. À remplir le jour où un
  // audit ou une feuille de route cite des codes, pour que l'écran y renvoie.
  documentation: { dossier: "docs", sources: [] },

  // Le seul chiffre du tableau de bord qui ait une limite réelle. `site.css` porte tout
  // le front en un seul fichier — 3 482 lignes aujourd'hui, la plus grosse pièce du
  // dépôt hors tests. Le seuil dit « au-delà, ce fichier demande à être découpé », pas
  // « c'est cassé » : c'est un budget de croissance, à régler à l'usage.
  //
  // La fenêtre est à 30 jours, et pas à 60, pour une raison mesurée : tout l'historique
  // du dépôt tient dans une salve du 1er au 14 juillet 2026, et une fenêtre de 60 jours
  // y attrape la CRÉATION du fichier, pas sa croissance. Le bandeau annonçait alors
  // « +3 482 / 300 », soit 1 160 % — un rouge qui ne mesurait que la naissance du
  // fichier. Sur 30 jours glissants il compte ce qu'on veut voir : ce que le mois écoulé
  // a ajouté. Il vaut 0 aujourd'hui, le dépôt étant sans commit depuis le 14 juillet.
  veille: { fichier: "front/static/css/site.css", seuil: 150, jours: 30 },
};
