# État d'implémentation

Carte des modules livrés et des **conventions transverses** à respecter pour
toute nouvelle contribution. Le cadrage fonctionnel de référence reste
`docs/cahier-des-charges-asso.md` ; ce document décrit ce qui *existe* et *comment
c'est structuré*.

> État : **v1 fonctionnelle complète**, ~670 tests pytest. Reste le déploiement
> VPS (fichiers dans `deploiement/`).

---

## Les trois faces

### Front public (`apps/vitrine`)
Accueil, spectacles (liste filtrable + détail), agenda (liste + calendrier +
export iCal), galerie, page association + fiches membres visibles, contact
(honeypot anti-spam + consentement RGPD ; envoi e-mail **non activé**, messages
persistés en base). Panneau d'accessibilité (préférences en cookie, classes
appliquées sur `<html>`, JS externe sans inline).

**Ce qu'une page publique annonce, et ce qu'elle tait** (VIT-4) :
`apps/agenda/services.py::prochaines_participations` construit les prochaines
dates d'un membre à partir des seules `Intervention` explicites sur un événement
publié ET public — figurer à la distribution d'un spectacle n'annonce aucune
date. La fiche montre les cinq plus proches puis renvoie à l'agenda, et le
décompte lit la liste affichée plutôt qu'une seconde requête. Le spectacle
rattaché à une date passe par `Evenement.spectacle_public` : non publié, il ne
paraît nulle part — ni agenda, ni fiche de la date, ni JSON-LD, ni image de
partage. La carte de date est une seule inclusion,
`front/templates/vitrine/_carte_agenda.html`, servie par l'agenda comme par la
fiche artiste.

**Confort de lecture** : la liste des sept classes posées sur `<html>` est
fermée des deux côtés — `apps/common/context_processors.py::CLASSES_CONFORT`
relit le cookie `a11y`, `front/static/js/accessibilite.js` ne bascule que
celles-là, et un test refuse que les deux listes divergent.

### Espace membre (`apps/espace_membre`) — connecté

**Page artiste : brouillon et publication** (VIT-4). `Membre` porte la version
**publiée** — celle que le site sert —, `BrouillonPageArtiste` le travail en
cours ; les champs éditoriaux vivent dans un jeu abstrait partagé
(`ContenuPublicArtiste`), pour qu'un champ ajouté d'un côté ne soit pas un champ
que « Publier » oublie. `apps/coeur/services.py::publier_page_artiste` relit la
fiche sous verrou et recopie tout d'un coup ; il RECOPIE (une biographie effacée
s'efface en ligne) et rend `False` quand il n'y avait rien de neuf. L'aperçu
(`apercu_ma_page`) sert le gabarit ET le contexte publics
(`vitrine/views.py::contexte_fiche_membre`) à partir d'une instance non
enregistrée : pas de seconde maquette à tenir à jour. Écrire `Membre` — bureau,
admin, services — c'est publier ; l'écran du bureau signale un brouillon en
attente, qui recouvrira sa saisie.
Tableau de bord (à traiter, prochaines dates, projets), **proposer son projet**
(spectacle) et **son événement**, chacun présenté d'abord en **fiche lecture**
(`voir_projet` / `voir_evenement`, URL `.../<pk>/`) avec bouton **Modifier**
(`editer_*`, URL `.../<pk>/modifier/`) et lien « Voir sur le site » si publié ;
répondre à ses
**convocations/CR d'AG** (présence / pouvoir), ses **reçus fiscaux**, et gérer
tous ses **fichiers** dans un explorateur unifié (« Fichiers »). Tout est filtré
par le membre connecté (voir *Anti-IDOR*).

**Explorateur « Fichiers » à quatre branches.** Un seul écran (`espace_membre.
mes_fichiers`) présente quatre branches, portées par `Dossier.espace` +
`Dossier.visibilite` :
- **Perso** : `espace=PERSO`, `proprietaire=membre`, `visibilite=PRIVE` — à lui seul ;
- **Partagé** : `espace=COMMUN` (`proprietaire` NULL) — espace **collaboratif** :
  tout membre y lit ET écrit (détail `dossier_commun`, URL `espace/commun/`) ;
- **Bureau** : `espace=PERSO`, `proprietaire=membre`, `visibilite=BUREAU` — transmis
  au bureau (consultable en agrégat via `backoffice:fichiers_membres`) ;
- **Association** : `espace=ASSOCIATION` (`proprietaire` NULL) — documents officiels
  de l'asso. **Éditable par le bureau** (dossiers, dépôt avec `confidentialite`,
  **versionnement**, suppression) ; **lecture seule filtrée par confidentialité**
  pour les membres (détail `dossier_association`, URL `espace/association/`).

La **branche est choisie à la création** (bouton par branche ; création Association
réservée au bureau) ; un **sous-dossier hérite de la branche de sa racine**
(services `creer_dossier_membre` / `creer_dossier_commun` / `creer_dossier_association`).
La même `dossier_detail.html` sert les quatre branches, pilotée par `peut_ecrire`
(= `est_proprio` / `est_bureau`) + les noms d'URL et `avec_confidentialite`.

**Accès (helpers `apps/espace_membre/views.py`).** L'accès à un document suit
l'espace de son dossier : `PERSO` → `_peut_voir_dossier_membre` (Perso =
propriétaire seul, **bureau exclu** ; Bureau = propriétaire + bureau) ; `COMMUN` →
`_peut_voir_espace_commun` (tout membre) ; `ASSOCIATION`/non classé → par
`confidentialite` (`_documents_accessibles` : bureau tout, `CONNECTES`→tout compte
connecté (valeur stockée `public`, libellé corrigé — il n'a jamais rien mis en ligne),
`MEMBRES`→membre, `PRIVE`→déposant). **Étanchéité** : chaque famille d'URL filtre
son espace (`get_object_or_404(..., espace=…)` → un pk d'un autre espace = 404) ;
l'écriture Association est gardée par `est_bureau` (POST non-bureau → 404).

### Back-office (`apps/backoffice`) — bureau
3ᵉ app métier (sans modèle propre), **interface sur-mesure** (templates sur
`base.html`, pas l'admin Django) : **tableau de bord** (compteurs + accès
rapides), **finances** (hub : porte d'entrée unique — chiffres clés facturation /
cotisations / **trésorerie** + tuiles « à traiter » vers les sections),
**modération** (valider/refuser projets et événements, fixer la
visibilité), **programmation** (gestion directe des **événements** et **projets** :
liste, création avec **publication immédiate** possible, édition de n'importe
quelle fiche même publiée, intervenants/distribution via formsets, porteurs en
cases à cocher, suppression — complète la modération ; la **mise en scène** n'a pas
de champ dédié : c'est une **ligne de distribution** au rôle libre « Mise en scène »),
**facturation** (un **écran unique à onglets** — Devis · Factures · Avoirs ·
Clients ; devis → transformation en facture ; facture brouillon → validation
numérotée → PDF ; **aperçu** ; **avoir**), **cotisations & reçus** (onglets
**adhésions** — par saison + statut + montants, personne choisie ou **créée à
la volée**, avec ou sans compte — et **reçus fiscaux** Cerfa),
**membres** (fiches ; création avec accès en ligne optionnel ; **ouverture
d'accès** a posteriori), **fichiers transmis** (agrégat en lecture des dossiers
que les membres marquent « transmis au bureau » ; la gestion documentaire
officielle est passée dans la branche **Association** de l'explorateur « Fichiers »),
**budget** (mouvements + bilan par catégorie + export Excel ; l'écran Bilan porte
un **tableau de bord** — chiffres clés, réalisé face au budget par catégorie,
répartition des dépenses — dessiné en **HTML/CSS**, sans SVG ni bibliothèque
cliente, avec le tableau détaillé pour jumeau accessible ; séries préparées par
`budget/graphiques.py`, qui ne calcule aucun montant ; **trésorerie** =
solde en banque de référence saisi par le trésorier + prévisionnel = solde +
reste à réaliser du budget de la saison — repère de gestion à rapprocher des
comptes, pas une compta),
**gouvernance** (réunions/AG : quorum, ordre du jour, présences avec
préremplissage des droits de vote, pouvoirs, résolutions avec résultat ;
**compte-rendu en déroulé** — note/décision par point + **blocs de récit
libre** (`BlocCompteRendu`) intercalables (préambule, échanges, transitions) +
conclusion — et **génération du PV en PDF** reprenant présences/pouvoirs/quorum/
résolutions, déposé dans la GED via `gouvernance.services.generer_compte_rendu`
(régénérer crée une **nouvelle version**, l'ancienne est conservée ; les écrans
servent la version courante, y compris quand le PV a été corrigé depuis la GED) ;
**édition de la réunion** — statut, convocation — hors admin),
**réglages** (paramètres de l'association, équipe = groupe « Bureau »). Listes
filtrables et paginées.

> L'admin Django (`/admin/`) reste disponible en parallèle pour la config rare
> et les CRUD techniques non couverts par un écran sur-mesure.

---

## Conventions transverses (à suivre absolument)

### Couche services
La logique métier vit dans un `services.py`, **pas dans les vues** (qui
orchestrent et rendent le retour utilisateur). Points d'entrée notables :
- `apps/common/moderation.py` : `soumettre_a_moderation`, `valider`, `refuser` ;
  `publier` (publication directe par le bureau, depuis n'importe quel état).
- `apps/common/fiches.py` : `ImagesFicheFormMixin` + `appliquer_images` — briques
  affiche/galerie mutualisées entre l'espace membre et le back-office (programmation).
- `apps/facturation/services.py` : `valider_facture` (numéro légal),
  `creer_avoir`, `transformer_en_facture`, `numeroter_devis`, rendus PDF.
- `apps/budget/services.py` : `emettre_recu`, `bilan_par_categorie`, PDF Cerfa ;
  `tresorerie` (solde en banque de référence + prévisionnel) ; `resume_cotisations`
  (chiffres du hub Finances). Facturation : `apps/facturation/services.py::resume_facturation`.
- `apps/coeur/services.py` : `creer_membre` (fiche seule, sans compte),
  `ouvrir_compte` (crée l'`Utilisateur` + lien d'activation), `synchroniser_compte`
  (recopie l'identité vers le compte sans toucher l'identifiant), `creer_compte_membre`
  (raccourci fiche + accès).
- `apps/gouvernance/services.py` : `figer_les_regles` (seuils du jour, à la
  clôture) et `contenu_scelle` (le contenu d'une séance close ne se réécrit plus,
  cf. « Résultat d'une réunion ») ; `ajouter_sujet_a_l_ordre_du_jour`,
  `enregistrer_resolution`, `saisir_presence`, `ajouter_bloc_de_recit`,
  `enregistrer_compte_rendu`, `donner_pouvoir`, `preremplir_droit_de_vote`,
  `generer_compte_rendu` (PV PDF). Tout ce qui écrit le contenu d'une réunion
  passe par l'un d'eux.
- `apps/documents/services.py` : `remplacer_document` (versionnement) ;
  `creer_dossier_membre`, `televerser_fichier_membre`, `modifier_dossier_membre`,
  `supprimer_dossier_membre`, `supprimer_document_membre` (espace « Mes fichiers »).
  Validation d'upload partagée : `apps/documents/validators.py`
  (`valider_fichier_document` : taille max + extensions exécutables refusées).

### Champs de formulaire : une seule convention d'identifiants
Django ≥ 5 relie lui-même l'aide et l'erreur d'un champ à son widget par
`aria-describedby` (`forms/boundfield.py::aria_describedby`), en nommant
`<auto_id>_helptext` et `<auto_id>_error`. **Le gabarit doit rendre ces id-là** ;
une référence vers un id absent est ignorée **sans erreur**, si bien que l'aide
s'affiche à l'écran et ne s'annonce jamais. Un mixin maison posait une seconde
convention (`_aide`) : tout formulaire qui l'oubliait pendait dans le vide. Il a
été retiré (lot 9 de SEC-1) — ne pas le réintroduire, et ne **pas** poser
`aria-describedby` à la main sur un widget : Django s'effacerait devant lui et le
rattachement de l'erreur serait perdu.

Le passage obligé est `front/templates/_champ.html`. **Vingt-cinq gabarits rendent
encore un champ à la main** et n'ont pas d'id sur leurs messages d'erreur : la
référence `_error` y pend dès qu'un formulaire est refusé, état qu'aucun balayage
ne visite. C'est un cas de l'inventaire ARCH-01. Un nouveau formulaire passe par
`_champ.html`, sans exception.

Trois invariants de balayage tiennent tout ça sur les 64 pages rendues
(`apps/common/tests.py`) : aucune référence `aria-*` dans le vide, aucun
identifiant rendu deux fois, un nom accessible pour chaque champ, bouton et lien.
Un formulaire rendu plusieurs fois sur une page doit porter un `auto_id` distinct
par copie (cf. `_form_dossier` dans `apps/espace_membre/views.py`).

### Images téléversées
Tout `Media` image est préparé à l'enregistrement (`medias/services.py`, appelé
par `Media.save()` — le seul point que tous les chemins traversent, admin
compris) : réduction à **2 000 px**, **vignette de 600 px**, dimensions
stockées. Le **format d'origine est conservé** (une transparence ne s'aplatit
pas, l'URL ne change pas) et le fichier réduit est réécrit **sous le même nom**,
par le stockage — `champ.save()` laisserait l'original à côté.

Le traitement est **idempotent** (sinon chaque `save` réencoderait) et
**silencieux** sur un fichier absent ou illisible : c'est un confort, il ne doit
pas faire échouer un téléversement. Remplacer le fichier d'un média jette les
dimensions et la vignette d'avant. Le stock antérieur se reprend par
`manage.py preparer_medias`.

Côté gabarits, un seul fragment — `front/templates/_image.html` — porte
`srcset` (vignette + image), `sizes`, `width`/`height` et le chargement différé.
`sizes` est indispensable : sans lui le navigateur suppose 100 % de la largeur
et reprend la grande image. **Toute** image d'un `Media` passe par ce fragment,
y compris les aperçus des écrans de gestion : ils indiquent leur taille
d'affichage (`largeur_affichee`), et les dimensions sont mises à l'échelle pour
garder le rapport. Un invariant de balayage vérifie que chaque `<img>` rendu
porte un attribut `alt` (règle 2), ce qui n'a de sens que parce que les objets
témoins portent de vraies images.

### Budget de requêtes
Une page publique ne doit pas voir son nombre de requêtes SQL suivre le nombre
d'objets affichés : `select_related` sur les affiches (cartes de spectacles),
`prefetch_related` sur les liens de réseaux des membres en vedette,
`select_related` sur l'événement, son lieu, son affiche et son spectacle pour
les participations d'un artiste. Les tests correspondants
(`apps/vitrine/tests.py`) comparent **3 objets et 12**, et non un total chiffré — un total se périme au premier préchargement ajouté ailleurs,
alors que « le nombre de requêtes ne suit pas le contenu » reste vrai.

Pagination partagée : `apps/common/pagination.py::paginer` (+ le gabarit
`front/templates/_pagination.html`), pour le back-office comme pour la galerie
publique, qui rassemble les images de tous les spectacles et événements publiés.

### Rôles & autorisation bureau
`apps/coeur/roles.py` est la **seule** porte : `est_bureau(user)` (groupe Django
« Bureau » **ou** `is_staff`/superuser, compte actif) et le décorateur
`@bureau_requis`. Ne jamais remettre un `is_staff` brut dans une vue. Le groupe
« Bureau » est créé par `apps/backoffice/migrations/0001`. `est_bureau` est
exposé aux gabarits par `apps.backoffice.context_processors.roles`.

### Anti-IDOR (espace membre)
Propriété vérifiée **par objet**, jamais par id d'URL nu :
- projets : `get_object_or_404(Spectacle, pk=pk, porteurs=membre)` ;
- événements / documents / reçus : filtre `cree_par=request.user` ou `membre=`.
- Ressource interdite → **404** (pas 403), pour ne pas révéler son existence.
- Champs sensibles verrouillés dans les formulaires membres (`type_portage`
  restreint, `visibilite` non exposée, `spectacle` limité aux projets du membre).

### Fichiers privés
Hors racine web (`apps/common/stockage.py::StockagePrive` →
`settings.MEDIA_PRIVE_ROOT`), servis uniquement par une vue authentifiée
contrôlant les droits, via `apps/common/fichiers.py::reponse_fichier_prive`
(X-Accel-Redirect en prod — cf. `deploiement/nginx-improliante.conf` ;
`FileResponse` en dev). Concerne documents, reçus, factures, images de signature.

### Documents PDF (WeasyPrint)
`apps/common/pdf.py::html_vers_pdf` importe WeasyPrint **paresseusement** (libs
natives requises seulement au rendu, sur le VPS). Les documents légaux (facture,
reçu) rendent leur PDF **dès l'émission** (`transaction.on_commit`) et le
conservent (privé, immuable) : l'émetteur, le signataire et les paramètres de
l'association sont lus AU RENDU, si bien qu'une pièce produite plus tard
raconterait l'association d'aujourd'hui. Sans moteur PDF, le rendu retombe sur le
1ᵉʳ téléchargement (`assurer_pdf_facture` / `assurer_pdf_recu`, qui revérifient
l'absence de fichier sous verrou) — le numéro, lui, reste attribué. L'aperçu
d'une pièce émise sert le fichier archivé ; devis rendu à la volée. Un
**signataire** optionnel (`coeur.Signataire`, image en base64) peut être apposé.

Chaque pièce émise porte en outre un **instantané** (champ JSON `instantane`,
cf. `apps/common/instantane.py`) : émetteur, client ou donateur, signataire —
fac-similé compris — lignes et totaux, tels qu'ils étaient ce jour-là. Le PDF
d'une pièce émise est rendu DEPUIS cet instantané : un fichier perdu se
reconstruit à l'identique, et non avec le nom que l'association porte
aujourd'hui. L'aperçu d'un brouillon, lui, part des données vivantes — c'est ce
qu'on veut vérifier avant d'émettre.

### Numérotation légale
`valider_facture` attribue un numéro **séquentiel, continu, sans trou** à la
validation, sous verrou (`select_for_update`) dans une transaction. Séquence
partagée facture/avoir (préfixe `F`/`A`). Idem `emettre_recu` (préfixe `R`).
Les devis sont numérotés plus souplement (préfixe `D`, sans criticité légale).

Toute transition relit sa pièce **sous verrou avant de la contrôler** : l'instance
reçue par un service peut être périmée (double clic, deux onglets), et tester son
état ne prouve rien. Vaut pour `valider_facture`, `transformer_en_facture`,
`creer_avoir`, `emettre_recu` (un versement = un seul reçu) et
`remplacer_document` (une seule version courante). L'édition d'un brouillon suit
la même règle : `form.save()` réécrit toute l'instance lue à l'ouverture de la
page, et effacerait le numéro d'une facture validée entre-temps.

> Nuance de test : SQLite rend `select_for_update` inopérant ; les tests
> valident les règles fonctionnelles, la sûreté concurrentielle repose sur
> PostgreSQL.

### Résultat d'une réunion
Le quorum se calcule sur le **registre électoral** de la réunion : tous les
électeurs y sont inscrits — absents compris — par `preremplir_droit_de_vote`
(membre actif, et à jour de cotisation si les statuts le demandent). Un registre
réduit aux présents ferait paraître le quorum atteint alors qu'il ne l'est pas.

À la **clôture** (statut « archivée »), les seuils statutaires du jour sont figés
dans `Reunion.regles_figees` et le registre ne se rouvre plus : modifier ensuite
quorum ou majorités dans les paramètres ne réécrit aucune assemblée passée. Avant
la clôture, les paramètres courants s'appliquent, pour qu'un seuil mal saisi reste
corrigeable. Les pouvoirs passent par un seul service — plafond statutaire
compris — que la saisie vienne du membre ou du bureau, et **quel que soit le
chemin** : l'inline de l'admin est en lecture seule, parce qu'il écrivait sans le
plafond et sans marquer le mandant « représenté ». Le retrait vit au même endroit
que la saisie (fiche de la réunion) et remet le mandant « absent ».

Le **contenu** est scellé par la même clôture, et c'est une règle distincte :
`contenu_scelle` refuse résolution, point d'ordre du jour, présence, pouvoir et
réécriture du compte rendu sur une réunion archivée. Elle est relue **sous
verrou** dans le service (la séance peut être archivée entre l'affichage de
l'écran et l'envoi du formulaire), et l'écran lit la même ligne pour ne plus
offrir les formulaires — sans quoi on remplit un écran pour se voir refuser à
l'envoi. L'admin l'applique aussi : inlines en lecture seule, décompte des voix
et notes d'un point figés, rattachement à une séance close refusé.

Deux exceptions, voulues : le **PV se régénère** (il ne fait que rendre un
contenu scellé ; le refuser enfermerait une séance sans son PV), et la réunion
**se rouvre par son statut** (une clôture par erreur doit se défaire). Son
en-tête reste figé, la réouverture s'annonce à l'écran, et les règles figées à la
clôture ne se refigent pas.

### Pièce émise et rattachements
Un reçu fiscal ne se retouche pas, ne se supprime pas, et **ne change pas de
rattachement** — l'admin le dit et le tient. Conséquence tirée au lot 15 : une
**adhésion dont un reçu a été émis ne se supprime plus** (`budget.services.
supprimer_adhesion`), sans quoi la pièce survivait en cessant de dire quelle
cotisation elle couvre. L'écran n'offre plus le bouton, l'admin refuse aussi, et
le message nomme le reçu. Les **transactions** liées restent détachées : une
écriture budgétaire est interne, elle n'est partie chez personne.

### Invariants d'une pièce émise
`valider_facture` refuse : une pièce déjà émise, une pièce sans ligne, un avoir
détaché de sa facture, un avoir qui annulerait plus que le reste à annuler, et
une pièce dont le total n'a pas le signe de son type — une facture ne rembourse
pas, un avoir ne facture pas. Les lignes, elles, gardent quantités et prix libres
de signe (une remise est une ligne négative légitime) ; la base borne seulement le
taux de TVA à [0, 100].

### Cycle de modération
`brouillon → proposé → publié / refusé` (mixin `apps.common.models.Moderation`),
réutilisé pour spectacles et événements. Le membre propose ; le bureau
valide/refuse (avec motif). Transitions gardées dans le service.
**Édition après publication** : l'auteur peut retoucher sa fiche **même publiée**
(brouillon, refusé et publié sont modifiables ; seul « proposé » est verrouillé
le temps du contrôle initial — helpers `peut_etre_edite_par_auteur` /
`peut_etre_soumis`). Une retouche d'une fiche publiée reste **en ligne** et lève
`Moderation.modifie_apres_publication` (`signaler_modification_apres_publication`) ;
le bureau la voit dans la file « À revoir » de `backoffice:file_moderation` et
l'acquitte via `marquer_projet_revu` / `marquer_evenement_revu` (service
`marquer_revu`). Republier depuis le back-office (`publier`) efface le drapeau.
La **visibilité** reste fixée par le bureau (jamais exposée au membre).

### Membre = personne, compte optionnel
`coeur.Membre` porte l'**identité** (`prenom`, `nom`, `email`) et le compte de
connexion (`user`, `OneToOne` nullable, `SET_NULL`) est **facultatif** : un
**adhérent peut exister sans accès en ligne**. `Membre.__str__` = `nom_complet`
puis e-mail puis identifiant du compte (jamais d'erreur si `user` est nul) ;
`a_un_compte` = présence d'un compte. Le tri et la recherche se font sur
`nom`/`prenom` (plus sur `user__…`). Le droit de vote en AG est indexé par
`membre_id`, donc un adhérent sans compte **vote quand même**. Limite assumée :
`synchroniser_compte` ne re-synchronise pas l'identifiant de connexion
(`username`) quand l'e-mail change (la connexion reste stable).

### Configuration paramétrable (jamais en dur)
Singletons éditables en admin : `coeur.ParametresAssociation` (identité légale
pour les documents), `gouvernance.ParametresGouvernance` (quorum, majorités,
pouvoirs). `coeur.Signataire` (référentiel de signataires habilités/délégataires).

---

## Qualité & tests

- **pytest + pytest-django** ; base SQLite en mémoire (`config/settings_test.py`),
  médias dans un dossier temporaire. `pytest -q`.
- **ruff** (`ruff.toml`, ligne 100, migrations exclues) : `ruff check .` / `ruff format .`.
- Le rendu PDF est **mocké** dans les tests (`html_vers_pdf` remplacé) : la suite
  tourne sans WeasyPrint.
- Zones traitées **test-first** : numérotation légale, quorum/résolutions,
  versionnement, anti-IDOR.
- **`TEST_POSTGRES=1 pytest`** rejoue la suite sur PostgreSQL. À faire avant
  toute mise en ligne : sous SQLite, `select_for_update` est un **no-op**, si
  bien que la numérotation légale (règle 4) y est validée dans sa règle mais
  jamais dans sa tenue en concurrence. Deux tests dédiés — factures et reçus
  fiscaux — lancent huit validations simultanées derrière une barrière et
  exigent huit numéros contigus ; ils se déclarent « skipped » sous SQLite
  plutôt que de passer sans rien prouver. Vérifiés par mutation : verrou
  retiré, ils échouent sur des numéros dupliqués.

---

## Reste à faire

- **Déploiement VPS** : Nginx + Gunicorn (systemd) + PostgreSQL + Certbot +
  webhook GitHub. Installer les libs natives de WeasyPrint (`libpango`, `libcairo`,
  `libgdk-pixbuf`, `libffi`). Fichiers prêts dans `deploiement/`.
- Pistes v2/v3 (hors périmètre sans demande, cf. cahier §15) : relances
  automatiques, interfaces sur mesure (explorateur de fichiers, éditeur de
  facture), newsletter, billetterie, gestion des bénévoles.
- Le **tableau de bord budget** (cahier §15, v2) est **fait** — cf. back-office
  ci-dessus et la fiche `pilotage/BUD-1.md`. Une courbe d'évolution mensuelle
  reste possible : c'est la seule vue écartée, faute d'agrégation temporelle.
- Le reste à faire vit dans `pilotage/`, confronté aux commits par l'outil
  `pilote` — un chantier par fiche, une QA visuelle par passe.
