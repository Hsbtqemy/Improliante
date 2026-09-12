# Audit approfondi d’Improliante

**Dépôt :** [Hsbtqemy/Improliante](https://github.com/Hsbtqemy/Improliante)  
**Révision examinée :** `8525e563fd61e8bb3b707e2a30ac3215a8993b99` — branche `main`, commit du 30 août 2026.  
**Date de l’audit :** 11 septembre 2026.  
**Périmètre :** architecture, permissions, documents, facturation, budget, gouvernance, front public, espace membre, administration, tests et déploiement.

## 1. Avis général

**Improliante constitue une bonne base de logiciel associatif sur mesure, mais plusieurs défauts confirmés doivent être corrigés avant de lui confier sans réserve des documents confidentiels et des opérations de facturation.**

Le projet est beaucoup plus avancé qu’une simple vitrine : il relie les personnes, leurs projets artistiques, les événements et plusieurs fonctions de gestion. Son architecture est adaptée à une petite association et à une maintenance assurée par peu de personnes. Je recommande de la consolider, sans refonte générale ni changement de framework.

La faiblesse principale tient à l’écart entre les garanties annoncées et leur application sur tous les chemins d’accès. Par exemple, la facture est présentée comme figée après validation, mais l’admin Django permet encore d’en modifier des éléments ; une réunion de bureau est inaccessible aux membres, mais son PV généré leur est accessible ; un filtre de propriété correct pour un membre devient permissif lorsque le compte n’a aucune fiche membre.

La suite existante est substantielle et passe dans cet environnement. Les défauts identifiés ne prouvent pas que les tests sont inutiles : ils montrent les scénarios qui leur manquent, notamment les identités atypiques, les documents dérivés, les objets relus avant une transition et les parcours alternatifs d’administration.

| Dimension | Appréciation | Enjeu principal |
|---|---|---|
| Architecture | Bonne base | Garder le monolithe ; mieux isoler politiques d’accès et transitions |
| Couverture fonctionnelle | Étendue | Consolider les modules sensibles avant d’en ajouter |
| Autorisations | Intentions solides, défauts importants | Corriger deux accès indus confirmés et préciser les rôles |
| Facturation et intégrité | Insuffisamment garanties | Idempotence, gel des données, cohérence avec l’admin |
| Front et expérience d’usage | Structure pertinente, finition incomplète | Fiabilité des formulaires, autonomie des auteurs, cohérence visuelle |
| Accessibilité | Fondations présentes | Vérification en navigateur et corrections des erreurs de formulaire |
| Exploitation | Préparée, non attestée | Déploiement conditionné aux tests, restauration et supervision |
| Tests | Bon socle | Élargir les scénarios plutôt que viser un nombre de tests |

Ces appréciations ne sont ni un score CVSS, ni une certification de sécurité, d’accessibilité ou de conformité juridique.

## 2. Méthode et limites

L’accès GitHub a permis d’identifier la branche et le commit, puis une copie locale de cette révision a été examinée. L’audit a porté sur les modèles, services, formulaires, routes, principaux templates, scripts front, configuration et scripts d’exploitation. Les références au code ci-dessous pointent sur le commit audité : elles restent stables si `main` évolue.

### Vérifications effectuées

| Vérification | Résultat | Portée |
|---|---|---|
| Installation de `requirements.txt` dans un environnement isolé | Réussie | Versions résolues le jour de l’audit, pas celles d’un éventuel serveur |
| Suite `pytest -q` | **520 réussis, 3 ignorés**, 241 avertissements, 7,30 s | SQLite ; les trois tests PostgreSQL de concurrence sont ignorés |
| `ruff check .` | Réussi | Analyse de style et règles de lint du dépôt |
| `manage.py check --deploy --fail-level WARNING` | Réussi | Configuration hors DEBUG, avec clé synthétique de test |
| `makemigrations --check --dry-run` | Aucun changement détecté | Cohérence entre modèles et migrations versionnées |
| Migration initiale sur base vide | Réussie | SQLite local uniquement |
| Reproductions ciblées | Plusieurs défauts confirmés | Données entièrement fictives ; aucun appel d’attaque au site déployé |
| Moteur WeasyPrint | PDF minimal généré, 5 381 octets | Disponibilité locale du moteur, pas validation de tous les documents métier |
| `pip-audit` | Alertes concernant le `pip` de l’environnement local ; aucune autre dépendance installée signalée | Ne décrit pas l’état d’un serveur inconnu |
| Front | Lecture HTML/CSS/JS et génération de neuf pages représentatives | Le navigateur a bloqué l’accès à l’aperçu local |

Environnement observé : Python **3.12.14**, Django **6.0.8**, django-treebeard **7.0.1**, WeasyPrint **70.0**. Le dépôt comporte **311 fichiers suivis**, dont **98 templates HTML**. La feuille CSS principale comporte **4 228 lignes**, soit environ **103 ko non compressés**.

Les copies HTML ont été produites par Django avec des données fictives pour l’accueil, les spectacles, l’association, l’agenda, l’espace membre, la création de projet, les fichiers, le bureau et la facture. **Aucune validation visuelle mobile/desktop, mesure Lighthouse, mesure de contraste globale ou interaction réelle au clavier n’a pu être menée.** Les recommandations d’ergonomie sont donc fondées sur le code et les parcours ; elles ne prétendent pas décrire une observation graphique du site en production.

Les tests HTTP ciblés utilisent le client de test Django, qui désactive la vérification CSRF par défaut. Les défauts d’autorisation décrits restent applicables à un compte connecté envoyant ses propres requêtes avec un jeton CSRF valide : ils ne supposent pas de contourner le CSRF.

Non vérifiés : historique Git complet, secrets éventuellement présents dans d’anciens commits, configuration effective du VPS, données réelles, sauvegardes distantes, permissions système réelles, TLS en production, charge simultanée et audit juridique des pièces émises. Les PDF utilisés pour reproduire les droits d’accès sont des fichiers synthétiques ; la reproduction du gel de facture inspecte le HTML transmis au moteur PDF.

## 3. Ce qui fonctionne bien et mérite d’être conservé

### 3.1 Un monolithe Django adapté au besoin

Le découpage en applications `coeur`, `spectacles`, `agenda`, `documents`, `facturation`, `budget`, `gouvernance` et modules d’interface est lisible. Le vocabulaire métier français facilite le dialogue entre code et fonctionnement associatif. PostgreSQL, templates Django, WeasyPrint et stockage de fichiers constituent un ensemble cohérent.

Le rendu serveur évite de maintenir deux applications et deux systèmes de validation. Le JavaScript reste concentré sur des améliorations locales : navigation, lignes de facture, formulaires et préférences d’affichage. Rien dans le besoin décrit ne justifie aujourd’hui une SPA générale ou des microservices.

**Attention documentaire :** DRF est installé, mais `rest_framework` est commenté dans les applications actives. L’application examinée utilise principalement des vues et templates Django ; sa présentation comme « Django + DRF » surestime le rôle effectif de l’API. [config/settings.py, ligne 81](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings.py#L81)

### 3.2 De bonnes protections sur les parcours ordinaires

Les projets du membre sont filtrés par `porteurs=membre`, et ses événements par `cree_par=request.user`. Les formulaires exposent des listes de champs explicites : un membre ne choisit pas arbitrairement son valideur, sa visibilité d’événement ou les porteurs d’un projet. Le formulaire d’événement restreint aussi les spectacles sélectionnables. [apps/espace_membre/views.py, ligne 251](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L251) [apps/espace_membre/forms.py, ligne 20](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/forms.py#L20)

L’authentification s’appuie sur Django, les mots de passe utilisent Argon2, le CSRF est actif, la clé secrète est exigée hors DEBUG, et plusieurs en-têtes/cookies de production sont configurés. Le lien d’activation réutilise un jeton Django expirant et invalidé après définition du mot de passe. [config/settings.py, ligne 51](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings.py#L51) [apps/coeur/services.py, ligne 162](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/coeur/services.py#L162)

Les templates conservent l’échappement par défaut. Le JSON-LD neutralise explicitement les caractères dangereux pour une balise `script`, et les textes de Bluesky passent par `textContent`. Je n’ai pas relevé d’injection SQL évidente dans les chemins examinés. Cela ne signifie pas que toute la surface est certifiée exempte de faille. [apps/vitrine/seo.py, ligne 50](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/seo.py#L50) [front/static/js/bluesky.js, ligne 45](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/js/bluesky.js#L45)

### 3.3 Une séparation physique pertinente des fichiers privés

Le stockage privé est séparé de `MEDIA_ROOT`, et la configuration Nginx prévoit une zone `internal` servie par `X-Accel-Redirect`. C’est un bon choix pour faire vérifier les permissions par Django sans monopoliser les workers lors du transfert des fichiers. Le problème identifié dans les PV se situe dans la classification et les autorisations, pas dans le principe du stockage. [apps/common/stockage.py, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/stockage.py#L1) [apps/common/fichiers.py, ligne 26](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/fichiers.py#L26) [deploiement/nginx-improliante.conf, ligne 36](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/nginx-improliante.conf#L36)

### 3.4 Une vraie attention aux transactions et aux usages

Les numéros de factures/reçus utilisent un compteur verrouillé ; les réservations verrouillent l’événement avant de consulter les places restantes. Cette dernière approche cible correctement la ressource partagée. Des transactions évitent également de conserver un client créé dans un formulaire de facture finalement invalide. [apps/agenda/services.py, ligne 98](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/agenda/services.py#L98) [apps/backoffice/views.py, ligne 1159](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1159)

La distinction entre personne adhérente et compte de connexion est pertinente pour une association. Les projets personnels, la modération, les fichiers personnels/partagés et les convocations répondent à des usages concrets. La possibilité de modifier un spectacle déjà publié est une décision éditoriale explicitement documentée, avec signalement au bureau : il faut la préserver ou la faire évoluer consciemment. [apps/common/moderation.py, ligne 73](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/moderation.py#L73)

### 3.5 Des bases d’accessibilité et de référencement déjà présentes

Liens d’évitement, labels, titres de sections, navigation sémantique, états `aria-expanded`, retour de focus du panneau d’accessibilité, gestion de la réduction des animations et textes alternatifs sont présents. Les assets typographiques sont locaux. Sitemap, robots, URL canoniques, métadonnées sociales et données structurées constituent un bon point de départ. [front/templates/base.html, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/base.html#L1) [front/static/js/accessibilite.js, ligne 70](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/js/accessibilite.js#L70) [apps/vitrine/sitemaps.py, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/sitemaps.py#L1)

Le panneau d’accessibilité ne remplace pas une vérification des pages sans options particulières. L’objectif doit rester une utilisation correcte dès les réglages par défaut.

## 4. Défauts à corriger avant usage sensible

**Priorités utilisées :** P0 = à traiter avant usage réel du module sensible ; P1 = prochain lot de consolidation ; P2 = amélioration planifiée. « Confirmé » signifie reproduit localement ou directement établi par la configuration/code indiqué. « Risque » précise une conséquence plausible dont l’occurrence réelle n’a pas été observée.

### SEC-01 — Suppression de documents officiels par un compte sans fiche membre

**P0 · Autorisation · Confirmé par requêtes HTTP locales.**

`supprimer_dossier_membre` et `supprimer_document_membre` récupèrent la fiche membre puis filtrent sur ce résultat, sans refuser `None` et sans imposer l’espace personnel.

Or les dossiers officiels et communs ont normalement `proprietaire=NULL`. Pour un utilisateur connecté sans fiche membre, le filtre ne désigne pas « ses dossiers » : il sélectionne les dossiers sans propriétaire.

**Reproduction :** compte actif ordinaire, ni staff ni bureau, sans `Membre` ; dossier de l’espace Association ; document confidentiel dans ce dossier. La suppression via la route personnelle renvoie **302** et supprime effectivement le document **et son fichier physique**. Un dossier officiel vide est également supprimé par la route personnelle.

**Condition d’exploitation :** disposer d’un compte connecté sans fiche membre et connaître/deviner un identifiant. Ce n’est pas une suppression anonyme. L’absence actuelle de comptes de ce type en production réduirait l’exposition, sans corriger le défaut.

**Correction :** refuser immédiatement les comptes sans membre sur ces opérations ; filtrer simultanément par identifiant, `espace=PERSO` et propriétaire ; centraliser la politique de suppression. Ajouter les cas « compte sans fiche », « membre d’autrui », « dossier commun », « dossier officiel » et « document sans dossier » aux tests négatifs.

**Acceptation :** ces requêtes renvoient 403/404 et ne modifient ni base ni stockage. Les suppressions autorisées continuent de fonctionner.

**Preuves :** [apps/espace_membre/views.py, ligne 829](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L829) [apps/espace_membre/views.py, ligne 847](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L847) [apps/documents/services.py, ligne 137](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/services.py#L137)

### SEC-02 — Les PV de bureau deviennent accessibles aux membres

**P0 · Confidentialité · Confirmé par téléchargement local.**

`generer_compte_rendu` crée systématiquement un document de confidentialité `MEMBRES`, sans dossier, quel que soit le type de réunion. Le contrôle de téléchargement accepte ces documents pour tout membre.

**Reproduction :** génération d’un PV de réunion de type `bureau`, puis téléchargement par un membre ordinaire : **HTTP 200**. La protection de la page de réunion n’empêche pas l’accès au document dérivé. Le document entre aussi dans le périmètre de la liste des documents associatifs accessibles.

**Correction :** déterminer l’audience du PV à partir de celle de la réunion. Par défaut, un PV de bureau doit rester bureau ; un PV d’AG doit suivre une politique explicite de diffusion. Vérifier également les PV déjà générés, car corriger seulement les nouveaux fichiers laisserait les anciens mal classés. Lors d’une régénération, conserver ou réévaluer l’audience selon une règle explicite.

**Acceptation :** un membre ne peut ni lister ni télécharger le PV d’une réunion de bureau, y compris par l’URL générique de document et après régénération.

**Preuves :** [apps/gouvernance/services.py, ligne 205](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/gouvernance/services.py#L205) [apps/espace_membre/views.py, ligne 486](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L486) [apps/espace_membre/views.py, ligne 511](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L511)

### FIN-01 — Une même facture peut être renumérotée

**P0 · Intégrité financière · Confirmé avec deux instances périmées.**

`valider_facture` vérifie le statut de l’objet Python reçu, puis verrouille le compteur annuel. Il ne recharge pas et ne verrouille pas la facture avant de vérifier qu’elle est encore brouillon.

**Reproduction déterministe :** lire deux instances A et B du même brouillon ; valider A ; valider B sans la recharger. Le premier appel attribue **F2026-0001**, le second **F2026-0002**. Il reste **une facture**, mais le compteur vaut **2** : le premier numéro n’est plus porté par la pièce.

Cette reproduction séquentielle établit le problème d’état périmé. Deux requêtes simultanées ayant lu le brouillon avant la première validation peuvent suivre la même séquence ; cette exécution simultanée sur PostgreSQL reste à ajouter aux tests.

**Correction :** service prenant un identifiant, transaction, relecture `select_for_update()` de la facture, validation de son état courant et de ses lignes, puis allocation du numéro. Toutes les écritures concurrentes sur une facture doivent respecter ce même protocole, y compris son édition : verrouiller uniquement la validation ne suffit pas si une édition ancienne peut ensuite réécrire le brouillon.

**Acceptation :** deux validations du même brouillon produisent une seule émission ; le deuxième appel retourne la pièce déjà émise ou une erreur métier contrôlée, sans consommer de numéro supplémentaire. Tester aussi l’édition concurrente avec la validation et le premier numéro de l’année.

**Preuves :** [apps/facturation/services.py, ligne 38](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/services.py#L38) [apps/backoffice/views.py, ligne 1195](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1195) [apps/facturation/tests.py, ligne 250](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/tests.py#L250)

### FIN-02 — L’immuabilité des factures n’est pas assurée sur tous les parcours

**P0 · Fiabilité documentaire · Plusieurs éléments confirmés.**

Trois mécanismes se cumulent :

1. La facture conserve des relations vers le client et le signataire ; le rendu lit les paramètres associatifs courants. Il n’existe pas de photographie complète de l’émetteur, du client et des mentions à la validation.
2. Le PDF est généré au premier téléchargement. Modifier le client entre validation et téléchargement modifie donc le document produit. La reproduction retrouve bien le **nouveau nom du client** dans le HTML de la facture déjà validée.
3. L’admin Django laisse éditables le client, le statut et les lignes ; il permet la suppression. Le formulaire personnalisé interdit l’édition après validation, mais cette protection n’est pas commune à tous les chemins. L’action admin de validation ne reprend pas non plus le contrôle « au moins une ligne » de la vue.

L’aperçu PDF est recalculé même pour une facture validée : il peut diverger du PDF archivé si des données liées ont changé.

**Correction :** figer à l’émission un snapshot versionné contenant identités, adresses, identifiants, mentions, coordonnées de paiement, signataire et lignes/montants. Produire le PDF depuis ce snapshot ; pour une pièce validée, l’aperçu doit représenter le même état que le téléchargement. Conserver le fichier et son empreinte. Restreindre l’admin aux opérations métier autorisées et interdire la suppression ordinaire des pièces émises. Une rectification doit être explicite, tracée et cohérente avec le traitement des avoirs.

Pour les pièces déjà émises, ne pas reconstruire arbitrairement un passé à partir des données courantes : inventorier les PDF archivés et les informations disponibles, puis documenter ce qui peut réellement être repris.

Le même examen est nécessaire pour les reçus : les données du donateur sont partiellement copiées, mais l’émetteur/signataire restent vivants et plusieurs champs ainsi que la suppression restent accessibles en admin.

**Acceptation :** changer le client, l’association ou le signataire n’altère pas une pièce déjà émise ; admin, vues et services respectent les mêmes règles ; un PDF manquant est régénéré depuis le snapshot historique.

**Preuves :** [apps/facturation/services.py, ligne 137](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/services.py#L137) [apps/facturation/admin.py, ligne 23](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/admin.py#L23) [apps/facturation/admin.py, ligne 58](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/admin.py#L58) [front/templates/facture/facture.html, ligne 61](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/facture/facture.html#L61) [apps/backoffice/views.py, ligne 1222](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1222) [apps/budget/admin.py, ligne 45](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/budget/admin.py#L45)

## 5. Sécurité, droits et gestion documentaire : consolidation

### SEC-03 — Les protections installées ne sont pas toutes actives

**P1 · Confirmé dans la configuration.**

`django-axes`, `django-otp`, `django-csp` et `django-simple-history` figurent dans les dépendances, mais leurs intégrations sont commentées ou absentes. Aucun mécanisme équivalent de limitation de tentatives n’a été trouvé dans le Nginx fourni. Le login est une `LoginView` Django standard.

Il faut distinguer les protections effectivement présentes — Argon2, CSRF, cookies sécurisés, paramètres HTTPS — de celles seulement prévues. Django ne limite pas par défaut les tentatives d’authentification [S2].

**Actions :** limitation des connexions avec traitement des erreurs et des adresses derrière proxy ; MFA pour les comptes privilégiés ; journal des actions métier sensibles ; CSP introduite en mode observation puis appliquée. Django 6 dispose d’un support CSP natif [S3] : choisir une seule intégration et sortir les scripts inline ou utiliser des nonces.

**Acceptation :** un test démontre le ralentissement/blocage des tentatives ; le MFA s’applique au bureau comme à l’admin ; chaque modification de rôle et émission documentaire possède un événement d’audit.

**Preuves :** [config/settings.py, ligne 81](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings.py#L81) [config/settings.py, ligne 111](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings.py#L111) [apps/espace_membre/urls.py, ligne 14](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/urls.py#L14) [deploiement/nginx-improliante.conf, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/nginx-improliante.conf#L1)

### SEC-04 — Le rôle Bureau est trop large pour une délégation fine

**P1 · Choix actuel confirmé ; risque selon l’organisation.**

`est_bureau` autorise le groupe Bureau, les superutilisateurs et **tout compte `is_staff`**. Les mêmes membres du bureau peuvent modifier l’appartenance au groupe, les paramètres associatifs, les pièces financières et la programmation.

Ce fonctionnement peut convenir à un bureau réduit où tout le monde dispose des mêmes responsabilités. Il ne permet pas de donner seulement la programmation à une personne, les finances à une autre ou un accès de lecture à un tiers. Un compte staff créé pour une fonction technique limitée reçoit aussi l’accès bureau complet.

**Proposition :** permissions métier indépendantes, regroupées en rôles ; permission spécifique de gestion des accès ; interdiction de retirer le dernier gestionnaire actif sans relais. Réserver `is_staff` à l’accès technique à l’admin. Les permissions par objet restent nécessaires pour les projets et fichiers, mais ne nécessitent pas automatiquement l’adoption de Guardian.

**Preuves :** [apps/coeur/roles.py, ligne 21](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/coeur/roles.py#L21) [apps/backoffice/views.py, ligne 534](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L534)

### SEC-05 — Distinguer fin d’adhésion, statut du membre et accès au compte

**P1 · Décision métier à formaliser.**

`Membre.actif`, les adhésions et `Utilisateur.is_active` sont des états distincts. Les principaux contrôles de l’espace membre vérifient la présence d’une fiche, sans exiger `Membre.actif`. Ce n’est pas forcément une erreur : un ancien adhérent peut légitimement conserver certains documents. Mais désactiver la fiche ne doit pas donner l’impression de révoquer l’accès au compte.

Prévoir un parcours de départ indiquant les accès conservés, la révocation des rôles, le transfert des projets collectifs et la conservation des documents. Tester chaque état plutôt que conditionner tous les accès au seul paiement d’une cotisation.

**Preuves :** [apps/coeur/models.py, ligne 93](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/coeur/models.py#L93) [apps/espace_membre/views.py, ligne 64](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L64) [apps/espace_membre/views.py, ligne 481](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L481)

### GED-01 — Le versionnement peut produire deux versions courantes

**P1 · Confirmé.**

`remplacer_document` crée une nouvelle version à partir de l’instance reçue, sans vérifier sous verrou que celle-ci est toujours courante. Remplacer deux fois la même ancienne version produit **deux successeurs v2 courants**. Une transaction ne suffit pas à empêcher cette bifurcation.

**Correction :** identité stable du document, table de versions et pointeur explicite vers la version courante ; ou verrouillage/relecture et contraintes assurant les mêmes invariants. Une ancienne version doit être consultable, sans pouvoir redevenir par inadvertance le point de départ courant.

**Acceptation :** deux remplacements concurrents ne créent jamais deux versions courantes ; le second utilisateur est informé du changement intervenu.

**Preuve :** [apps/documents/services.py, ligne 144](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/services.py#L144)

### GED-02 — Suppression immédiate, absence de corbeille et fichiers orphelins

**P1 · Confirmé par lecture du code.**

La suppression d’un document efface le fichier avant la ligne de base. Si la seconde étape échoue, le document peut rester référencé sans son fichier. Les fichiers partagés peuvent être supprimés par tout membre : c’est cohérent avec l’espace collaboratif actuel, mais amplifie les conséquences d’une erreur. La régénération d’un PV remplace le fichier précédent sans utiliser le versionnement documentaire.

Inversement, retirer une affiche, une photo ou une image de galerie détache la relation en conservant le média et le fichier. Cela entraîne une accumulation ; le retrait d’une page ne rend pas forcément l’ancienne URL inaccessible.

**Actions :** corbeille avec restauration, journal des suppressions, purge différée après validation de la transaction, versionnement des PV et tâche d’inventaire des fichiers orphelins. Établir une règle explicite pour l’audience des médias des brouillons : ils sont stockés dans la zone publique même si la page du projet n’est pas publiée.

**Preuves :** [apps/documents/services.py, ligne 137](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/services.py#L137) [apps/gouvernance/services.py, ligne 241](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/gouvernance/services.py#L241) [apps/spectacles/services.py, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/spectacles/services.py#L1) [apps/medias/models.py, ligne 30](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/medias/models.py#L30)

### GED-03 — Les quotas globaux et le traitement des fichiers restent à construire

**P1 pour les quotas, P2 pour les protections complémentaires.**

Les formulaires limitent les images à 5 Mio et les documents à 20 Mio. Nginx limite chaque requête. Ces protections n’empêchent pas un compte d’accumuler un grand nombre de fichiers. La GED utilise une liste noire d’extensions, sans analyse antivirus ; les documents sont servis en téléchargement, ce qui réduit certaines expositions mais ne protège pas la personne qui ouvre un fichier piégé.

Prévoir quotas par membre/association, visibilité de l’espace consommé, contrôle des dimensions d’image, réencodage des images publiques, variantes optimisées et politique d’extensions adaptée aux usages. Centraliser les validations pour couvrir aussi l’admin. Un contrôle de signature ou antivirus constitue une défense complémentaire, pas une garantie universelle de sûreté des fichiers [S2].

**Preuves :** [apps/common/fiches.py, ligne 15](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/fiches.py#L15) [apps/documents/validators.py, ligne 17](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/validators.py#L17) [apps/documents/models.py, ligne 102](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/models.py#L102)

### PUB-01 — Les formulaires publics restent exposés aux abus

**P1 · Risque établi par l’absence de mécanisme de débit.**

Contact et réservations disposent d’un champ piège. Un programme peut simplement le laisser vide. Le plafond de dix places s’applique à une réservation, pas à une succession de réservations ; il reste possible de saturer artificiellement une jauge. Le message de contact ne fixe pas de longueur métier explicite.

Ajouter une limitation de débit, une borne de message, des signaux de détection et un parcours d’annulation/recouvrement. Si l’usage le nécessite, prévoir une confirmation de réservation avec expiration des demandes non confirmées. Éviter de rendre un CAPTCHA obligatoire sans preuve d’un besoin.

**Preuves :** [apps/vitrine/forms.py, ligne 8](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/forms.py#L8) [apps/vitrine/forms.py, ligne 33](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/forms.py#L33) [apps/vitrine/views.py, ligne 319](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L319) [apps/agenda/services.py, ligne 98](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/agenda/services.py#L98)

### PUB-02 — Documentation de confidentialité incomplète

**P1 · Écart documentaire confirmé.**

La page de confidentialité se présente explicitement comme un modèle à compléter et décrit principalement le contact, alors que l’application traite aussi comptes, adhésions, réservations, documents, photos et gouvernance. La commande de purge des inscriptions existe, avec simulation par défaut : c’est utile, mais son exécution planifiée n’est pas établie.

Réaliser un inventaire des traitements et de leurs durées, puis aligner page d’information, procédures et automatisations. Le flux Instagram est récupéré côté serveur, mais les images distantes sont chargées par le navigateur si le flux est affiché ; ce point mérite d’être décrit dans les choix relatifs aux services tiers. Il s’agit ici d’un constat technique et documentaire, pas d’une qualification juridique de conformité.

**Preuves :** [front/templates/vitrine/confidentialite.html, ligne 7](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/confidentialite.html#L7) [apps/agenda/management/commands/purger_inscriptions.py, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/agenda/management/commands/purger_inscriptions.py#L1) [front/templates/vitrine/accueil.html, ligne 71](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/accueil.html#L71)

## 6. Backend : intégrité et maintenabilité

### FIN-03 — Transformation devis → facture non idempotente

**P1 · Confirmé.**

Deux instances anciennes d’un même devis, transformées successivement, créent deux factures. Le service vérifie l’état de l’instance mais ne recharge pas le devis sous verrou. La relation `devis_origine` n’impose pas l’unicité.

Verrouiller et relire le devis ; décider si le métier autorise une seule facture ou plusieurs facturations partielles. Dans le premier cas, ajouter une contrainte d’unicité ; dans le second, modéliser explicitement les acomptes et le solde. Tester les doubles clics et relances réseau.

La numérotation des devis est également calculée à partir du maximum existant, sans verrou ni unicité du champ. Supprimer le dernier devis permet de réutiliser son numéro, contrairement au commentaire qui annonce l’inverse. Un compteur dédié ou un identifiant d’émission non réutilisable est préférable.

**Preuves :** [apps/facturation/services.py, ligne 161](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/services.py#L161) [apps/facturation/services.py, ligne 196](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/services.py#L196) [apps/facturation/models.py, ligne 108](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/models.py#L108)

### FIN-04 — Mieux définir les invariants des pièces et des montants

**P1 · Lacunes de modèle et de validation.**

La validation « facture avec au moins une ligne » est située dans une vue et non dans le service. Quantité, prix et TVA n’ont pas de règle métier complète au niveau du modèle. Il faut distinguer une facture, un avoir et une éventuelle remise plutôt qu’interdire indistinctement tous les nombres négatifs.

`creer_avoir` refuse un brouillon et un avoir, mais ne vérifie pas les montants déjà annulés par d’autres avoirs. Plusieurs avoirs complets peuvent donc être créés pour la même facture. L’interface de budget proposée ne constitue pas, à elle seule, une comptabilité exhaustive : le rapprochement entre paiement d’une facture, cotisation et transaction doit avoir une règle explicite afin d’éviter oublis et doubles comptes.

**Actions :** formaliser états et transitions ; contraintes simples en base ; règles composites dans les services ; suivi des paiements et rapprochement si nécessaire ; traçabilité des corrections. Ne pas ajouter un grand système comptable sans besoin : une gestion de trésorerie clairement délimitée peut suffire.

**Preuves :** [apps/facturation/models.py, ligne 61](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/models.py#L61) [apps/facturation/services.py, ligne 70](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/services.py#L70) [apps/backoffice/views.py, ligne 1195](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1195) [apps/backoffice/forms.py, ligne 169](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/forms.py#L169)

### GOU-01 — Le résultat d’une réunion doit être figé avec ses règles

**P1 · Risques métier établis par le code.**

Le quorum utilise comme électorat les seules présences enregistrées avec droit de vote. Si le registre des votants n’est pas complet, le résultat peut surestimer la participation. Exemple : vingt membres éligibles mais seulement cinq présences enregistrées et votantes peuvent conduire à un calcul sur cinq, sans représenter l’électorat total attendu.

Les paramètres de majorité et de quorum sont relus dans leur configuration courante. Modifier ces paramètres peut modifier le résultat affiché d’une ancienne réunion. La commande de préremplissage des droits n’interdit pas de recalculer une réunion déjà tenue. Les pouvoirs du parcours bureau sont enregistrés directement, alors que le parcours membre applique un service plus contraignant ; le plafond est signalé, mais n’est pas uniformément imposé. Le calcul du plafond côté membre n’est pas verrouillé, d’où un risque de dépassement en concurrence.

**Actions :** registre électoral complet pour chaque réunion ; snapshot des règles et des droits au moment décidé ; gel à la clôture ; corrections motivées ; service unique des pouvoirs pour les différents parcours. Les seuils et modes de calcul doivent suivre les statuts réels. Le comportement d’arrondi actuellement documenté doit être testé aux limites et approuvé comme convention métier.

**Acceptation :** une modification des paramètres généraux ne change pas une réunion close ; les membres absents n’ont pas disparu du dénominateur ; un plafond de pouvoirs ne peut être dépassé par deux demandes simultanées sans décision explicite du bureau.

**Preuves :** [apps/gouvernance/services.py, ligne 52](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/gouvernance/services.py#L52) [apps/gouvernance/services.py, ligne 146](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/gouvernance/services.py#L146) [apps/gouvernance/services.py, ligne 173](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/gouvernance/services.py#L173) [apps/backoffice/views.py, ligne 1844](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1844) [apps/backoffice/views.py, ligne 1860](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/backoffice/views.py#L1860)

### ARCH-01 — Les règles centrales restent trop dépendantes des vues

**P1 · Maintenance.**

`apps/backoffice/views.py` atteint **1 981 lignes** et `apps/espace_membre/views.py` **1 267 lignes**. La longueur seule n’est pas un défaut fonctionnel, mais ces fichiers mélangent plusieurs domaines, requêtes de lecture et règles d’autorisation. Les helpers `_peut_acceder_document` ou `_dossiers_membre_visibles` portent une politique importante dans un module d’interface.

**Refactorisation ciblée :**

- Découper les vues par domaine dans des packages `views/`, en conservant les noms de routes.
- Sortir les permissions dans `documents/policies.py`, `spectacles/policies.py`, etc.
- Regrouper les requêtes de lecture réutilisées dans des fonctions dédiées.
- Faire des services les seules portes d’entrée des transitions sensibles.
- Donner aux erreurs métier des exceptions explicites et des retours utilisateur cohérents.

Éviter les couches abstraites sans usage, les repositories génériques autour de l’ORM et les wrappers de chaque opération simple. Priorité aux endroits où une règle doit être identique dans deux interfaces.

### ARCH-02 — Les modifications concurrentes des fiches peuvent se perdre

**P2 · Risque.**

Les formulaires de projet et de profil sauvegardent l’instance courante sans numéro de révision soumis avec le formulaire. Deux auteurs ou un auteur et le bureau peuvent écraser une modification précédente. Les opérations membre combinant texte, images et relations ne sont pas toutes atomiques.

Ajouter un contrôle optimiste de révision aux fiches collaboratives : en cas de conflit, présenter les deux versions ou demander une fusion. Regrouper les changements cohérents dans une transaction, en tenant compte du fait que le stockage de fichiers ne participe pas automatiquement au rollback SQL.

**Preuves :** [apps/espace_membre/views.py, ligne 142](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L142) [apps/espace_membre/views.py, ligne 251](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L251) [apps/common/fiches.py, ligne 88](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/fiches.py#L88)

### PERF-01 — Quelques requêtes et médias croîtront avec le contenu

**P2 · Un N+1 mesuré ; autres risques à mesurer.**

La liste publique des spectacles charge les affiches dans les cartes sans `select_related('affiche')`. Avec huit spectacles possédant une affiche, la requête HTTP locale produit **neuf requêtes SQL** : une pour la liste et une par affiche. C’est facile à corriger. L’accueil présente le même motif.

La galerie et plusieurs listes ne sont pas paginées. Les images sont servies dans leur format original, sans chaîne de vignettes/`srcset` repérée. Une image de 5 Mio peut donc être utilisée dans une petite carte. Le cache Instagram est le cache local par défaut de Django, et sa récupération peut bloquer un worker jusqu’au timeout à froid.

**Actions :** préchargements ciblés et budgets de requêtes ; pagination selon les volumes ; images redimensionnées avec variantes et dimensions connues ; mesure du temps de réponse ; mise à jour du flux social hors requête utilisateur si nécessaire. Ne pas introduire Redis ou une file de tâches uniquement par principe.

**Preuves :** [apps/vitrine/views.py, ligne 38](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L38) [apps/vitrine/views.py, ligne 55](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L55) [front/templates/vitrine/_carte_spectacle.html, ligne 3](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/_carte_spectacle.html#L3) [apps/common/instagram.py, ligne 28](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/instagram.py#L28)

## 7. Front : améliorations concrètes

### FRONT-01 — Fiabiliser d’abord la saisie des factures

**P1 · Deux défauts confirmés.**

**Totaux divergents.** JavaScript additionne des produits non arrondis, puis formate le total. Python arrondit chaque ligne au centime avant la somme. Trois lignes avec quantité **0,33**, prix **0,05 €**, TVA nulle donnent **0,06 € au serveur** et un total brut de **0,0495 € en JavaScript**, affiché **0,05 €**. Le sujet dépasse les seules imprécisions binaires : la convention d’arrondi diffère.

**Erreurs invisibles.** Le fragment des lignes affiche les erreurs de désignation, mais pas celles de quantité, prix ou TVA. Un formulaire avec quantité non numérique est invalide et contient l’erreur « Saisissez un nombre. » ; le HTML rendu ne contient pas ce message.

**Correction :** partager une convention décimale et des exemples de référence front/back ; afficher chaque erreur près de son champ, avec un résumé au début du formulaire et un lien vers la ligne concernée. Le serveur demeure l’autorité, mais l’estimation visible doit donner le même montant.

**Acceptation :** montants identiques pour arrondis, avoirs, TVA et lignes supprimées ; aucune soumission refusée sans explication accessible.

**Preuves :** [front/static/js/facturation.js, ligne 43](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/js/facturation.js#L43) [apps/facturation/models.py, ligne 77](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/facturation/models.py#L77) [front/templates/backoffice/_ligne_facturation.html, ligne 23](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/backoffice/_ligne_facturation.html#L23)

### FRONT-02 — Éviter de valider une ancienne version du brouillon

**P1 · Risque de parcours directement visible dans le template.**

Le formulaire d’édition et le formulaire « Valider et numéroter » sont distincts. Une personne peut modifier les champs, puis cliquer sur Valider sans avoir enregistré : la validation porte sur la version sauvegardée, pas sur les valeurs visibles. L’aperçu PDF ouvre lui aussi les données déjà enregistrées.

**Parcours proposé :** état visible « Modifications non enregistrées » ; validation désactivée tant que le brouillon n’est pas sauvegardé, ou action unique « Enregistrer puis vérifier » ; écran de confirmation montrant client, lignes, total et date ; émission seulement de la révision ainsi vérifiée. Compléter cela par les protections serveur de FIN-01 : le bouton seul ne règle pas le problème.

**Preuve :** [front/templates/backoffice/facture_form.html, ligne 16](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/backoffice/facture_form.html#L16)

### FRONT-03 — Achever l’amélioration progressive et retirer les outils de développement

**P1 pour la mise en production, P2 pour les raffinements.**

Le sélecteur de développement avec **18 palettes**, fonds et typographies est présent dans `base.html` sans condition DEBUG. Il augmente la complexité des états à tester et les liens `?theme=…` remplacent les autres paramètres de recherche. Il doit être retiré de l’interface courante ou réservé à un outil de conception.

Le bouton « Ajouter une ligne » est visible sans JavaScript, alors que son action dépend du script. Les totaux y restent des tirets. Une ligne supplémentaire peut être obtenue au fil des enregistrements grâce au formset, mais cette mécanique n’est pas explicitée. Le bouton d’accessibilité est également affiché sans son script.

**Actions :** une palette de référence éprouvée ; préférences utiles conservées séparément ; contrôles dépendant du JS masqués puis révélés après initialisation ; solution serveur pour ajouter une ligne et calculer le total ; message explicite si certaines commodités ne sont pas disponibles.

**Preuves :** [front/templates/base.html, ligne 131](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/base.html#L131) [front/templates/backoffice/facture_form.html, ligne 49](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/backoffice/facture_form.html#L49) [front/static/js/facturation.js, ligne 151](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/js/facturation.js#L151)

### FRONT-04 — Transformer la fiche spectacle en vraie page de présentation

**P2 · Opportunité produit liée au besoin exprimé.**

Le formulaire membre collecte genre, public visé et durée, mais la fiche publique examinée se concentre sur affiche, synopsis, note d’intention, distribution et dates. Elle ne valorise pas toute cette information. Les images de galerie sont gérées dans l’édition et la galerie générale, sans section de galerie sur cette fiche. « Prochaines dates » n’exclut pas les représentations passées dans la vue.

**Composition proposée :**

1. Titre, affiche, courte accroche et statut artistique.
2. Genre, durée, public conseillé et porteurs du projet.
3. Prochaine représentation, lieu et bouton de réservation lorsqu’il existe.
4. Synopsis, distribution et note d’intention en sections distinctes.
5. Galerie, liens externes et contact de programmation, selon les champs effectivement disponibles.
6. Dates passées dans une section d’archives séparée.

Le visiteur doit comprendre rapidement ce qu’est le spectacle, où le voir et comment contacter l’association. Un lien vers les profils publics des porteurs renforce l’utilité des pages personnelles. Un slug lisible pour les spectacles est une amélioration de partage, pas une protection de sécurité ; conserver les anciennes URLs via redirection.

**Preuves :** [apps/espace_membre/forms.py, ligne 30](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/forms.py#L30) [front/templates/vitrine/spectacle_detail.html, ligne 23](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/spectacle_detail.html#L23) [apps/vitrine/views.py, ligne 76](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L76)

### FRONT-05 — Donner plus d’autonomie aux auteurs sans leur déléguer la publication initiale

**P2 · Proposition.**

Conserver le formulaire simple, mais le structurer en sections « Présentation », « Informations pratiques », « Images » et « Publication ». Ajouter un aperçu de la fiche publique, des indications sur les formats d’affiche, et un repère clair sur ce qui sera public.

Pour les créations collectives, le modèle accepte plusieurs porteurs, mais le formulaire membre ne permet pas de gérer une collaboration ou la distribution. Prévoir un parcours dédié d’invitation/validation des coporteurs si l’usage le justifie, plutôt que d’ouvrir librement le champ M2M. La contribution artistique et le droit d’édition peuvent être distincts.

Pour un projet déjà publié, conserver la règle voulue d’édition immédiate, mais donner au bureau un **diff**, l’auteur, la date et une possibilité de restauration. Le drapeau `modifie_apres_publication` signale qu’il s’est passé quelque chose, sans conserver ce qui a changé. Une variante facultative serait un brouillon de révision conservant l’ancienne page en ligne ; ce serait une évolution métier, pas une correction obligatoire de la règle actuelle.

**Preuves :** [apps/espace_membre/forms.py, ligne 20](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/forms.py#L20) [apps/espace_membre/views.py, ligne 195](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L195) [apps/common/moderation.py, ligne 73](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/moderation.py#L73)

### FRONT-06 — Clarifier les audiences et sécuriser les gestes de fichiers

**P1/P2 · Proposition fondée sur les risques constatés.**

Les branches Perso, Partagé, Bureau et Association sont utiles. Chaque document/dossier doit néanmoins annoncer son audience en langage direct : « Moi uniquement », « Toute la troupe », « Moi et le bureau », « Membres autorisés ».

Un déplacement changeant l’audience d’un sous-arbre doit afficher avant confirmation le nombre de dossiers/documents concernés et les nouveaux destinataires. La suppression devrait offrir restauration et feedback. Ajouter recherche, taille, auteur, date et historique selon les besoins ; éviter de charger l’arbre entier si la volumétrie augmente.

Le niveau documentaire `PUBLIC` signifie actuellement « tout utilisateur connecté » dans le téléchargement générique, non accès anonyme. Renommer ce niveau ou réaliser un accès public explicitement conçu : le mot choisi doit refléter l’audience réelle.

**Preuves :** [apps/espace_membre/views.py, ligne 486](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L486) [apps/espace_membre/views.py, ligne 772](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py#L772) [apps/documents/services.py, ligne 168](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/documents/services.py#L168)

### FRONT-07 — Finir les parcours d’accès et de réservation

**P1/P2.**

L’activation existe, mais aucun parcours « mot de passe oublié » n’est défini dans les routes examinées. Il faut aussi traiter un lien expiré, sa réémission et le changement d’adresse, sans dépendre d’une opération technique improvisée.

Les réservations sont consultables par jeton, avec annulation : bon choix pour éviter d’imposer un compte. Ajouter un moyen clair de conserver ce lien, puis son envoi lorsque le mail est opérationnel. Prévoir les événements passés ou fermés : le service `inscrire` vérifie la jauge, mais pas une date de clôture ni le fait que l’événement soit passé. Le statut publié/public est vérifié par la vue avant l’appel, pas relu comme condition métier sous verrou.

**Preuves :** [apps/espace_membre/urls.py, ligne 12](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/urls.py#L12) [apps/vitrine/views.py, ligne 359](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L359) [apps/agenda/services.py, ligne 98](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/agenda/services.py#L98)

### FRONT-08 — Corriger les entrées invalides et vérifier l’accessibilité réelle

**P1 pour le défaut HTTP ; P2 pour la campagne complète.**

L’année du calendrier n’est pas bornée. `?vue=calendrier&annee=0&mois=1` produit un **HTTP 500** local. Les années extrêmes peuvent aussi dépasser les limites lors du calcul du mois voisin. Valider une plage utile, puis retourner un choix par défaut ou une erreur contrôlée.

Pour l’accessibilité, procéder ensuite à une campagne sur les écrans représentatifs : 375 px et desktop, zoom 200/400 %, navigation clavier, focus après erreurs, ordre des titres, lecteur d’écran, contraste de la palette retenue, formulaires longs et tableaux. Utiliser les tests automatiques pour détecter des défauts, puis une validation manuelle pour les usages. Le panneau de préférences ne justifie pas à lui seul une affirmation « conforme AA ».

**Preuves :** [apps/vitrine/views.py, ligne 169](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py#L169) [front/templates/backoffice/_ligne_facturation.html, ligne 23](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/backoffice/_ligne_facturation.html#L23)

## 8. Déploiement et exploitation

### OPS-01 — Le déploiement n’attend pas une validation distante du commit

**P1 · Confirmé dans les scripts et métadonnées disponibles.**

Le webhook signé HMAC déclenche le déploiement après un push sur `main`. Un hook pré-push local exécute les tests PostgreSQL, mais il doit être installé dans chaque clone et peut être contourné ; une édition via GitHub ne l’exécute pas. Le script de déploiement effectue un contrôle de configuration, pas une suite de tests métier.

GitHub indique `protected=false` pour la branche examinée et renvoie une liste vide de rulesets. Aucun workflow `.github/workflows` n’est versionné dans l’arbre audité. Cela n’exclut pas un service CI externe non visible, mais aucune barrière distante effective n’est établie.

**Cible :** checks PostgreSQL obligatoires avant intégration dans `main`, puis déploiement du SHA exact validé. Le hook local peut rester un confort. La remarque du dépôt selon laquelle une CI arriverait après le déploiement décrit la chaîne actuelle ; il suffit de changer le déclenchement pour en faire une vraie barrière.

**Preuves :** [deploiement/hooks/pre-push, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/hooks/pre-push#L1) [deploiement/deploy.sh, ligne 59](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/deploy.sh#L59) [deploiement/webhook_receiver.py, ligne 114](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/webhook_receiver.py#L114)

### OPS-02 — Déploiement en place et dernier push potentiellement perdu

**P1 · Mécanismes confirmés, incidents non simulés.**

Le script met à jour le code, le même environnement Python, la base et les statiques avant de redémarrer. Un échec intermédiaire peut laisser un assemblage partiellement mis à jour. Il n’y a pas de health check applicatif final ni de mécanisme de retour à une release précédente.

Le verrou `flock --nonblock` abandonne un deuxième déploiement. Si ce push arrive après le `fetch` du premier, le dernier commit n’est pas déployé automatiquement ; le commentaire le reconnaît.

**Actions :** file/coalescence des demandes jusqu’au dernier SHA attendu ; releases séparées et bascule contrôlée ; contrôle de santé après démarrage ; stratégie de migrations compatibles ; journal du SHA actif et notification d’échec. Un rollback du code n’annule pas magiquement une migration destructive : cette distinction doit figurer dans la procédure.

L’application tourne aussi sous `deploy`, comme le code et les opérations de livraison. Séparer utilisateur d’exécution et utilisateur de déploiement limiterait les conséquences d’une compromission applicative ; vérifier les permissions de fichiers effectives lors de l’installation.

**Preuves :** [deploiement/deploy.sh, ligne 29](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/deploy.sh#L29) [deploiement/deploy.sh, ligne 95](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/deploy.sh#L95) [deploiement/asso.service, ligne 18](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/asso.service#L18)

### OPS-03 — La sauvegarde peut réussir sans copie distante

**P1 · Défaut de signalement confirmé par lecture du script.**

La sauvegarde inclut bien base, médias publics et privés. Mais, contrairement à son commentaire, lorsque `RCLONE_REMOTE` est vide, elle affiche un avertissement puis continue jusqu’au message final et à la purge locale. **Le script ne renvoie pas explicitement un échec pour cette absence de copie distante.** Un ordonnanceur peut donc la considérer réussie.

**Correction :** état distinct et non nul si l’externalisation requise n’a pas eu lieu ; alerte ; contrôle des fichiers reçus ; procédure de restauration sur environnement vierge ; rétention/chiffrement selon la destination choisie. Vérifier aussi l’authentification PostgreSQL du cron : le commentaire mentionnant l’utilisateur `postgres` ne suffit pas à rendre valide `pg_dump -U asso` avec une authentification peer standard.

**Acceptation :** la perte simulée du VPS est récupérable depuis la copie distante, avec une durée de restauration et une perte maximale de données mesurées. Les sauvegardes base et fichiers doivent rester cohérentes malgré leur réalisation successive.

**Preuve :** [deploiement/backup.sh, ligne 27](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/backup.sh#L27) [deploiement/backup.sh, ligne 53](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/deploiement/backup.sh#L53)

### OPS-04 — Dépendances non verrouillées et documentation vieillissante

**P1/P2.**

Les versions reposent principalement sur des minimums, sans lockfile. Deux installations du même commit peuvent utiliser des versions majeures différentes. La suite actuelle produit notamment des avertissements de dépréciation liés à Treebeard. Les outils de développement sont installés avec les dépendances de production.

Verrouiller l’environnement testé, séparer runtime et développement, déclarer la version Python et automatiser les mises à jour contrôlées. Le README annonce Python 3.11+, alors que Django 6 exige au moins Python 3.12 [S4]. Il annonce aussi environ 168 tests et un état de déploiement qui doit être rapproché du suivi réel ; `CLAUDE.md` mentionne environ 400 tests, contre 520 réussis dans cet audit.

`pip-audit` a signalé uniquement le `pip` local créé avec l’environnement virtuel ; ce résultat ne permet pas d’annoncer des vulnérabilités du serveur. Il faut auditer les versions effectivement déployées et conserver leur inventaire.

**Preuves :** [requirements.txt, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/requirements.txt#L1) [README.md, ligne 10](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/README.md#L10) [README.md, ligne 46](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/README.md#L46) [config/settings_test.py, ligne 1](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings_test.py#L1)

## 9. Architecture cible proposée

La cible conserve Django, PostgreSQL, le rendu serveur et les applications métier. Elle introduit trois responsabilités explicites là où elles apportent une garantie :

| Responsabilité | Contenu | Exemple |
|---|---|---|
| Politique d’accès | Qui peut lire/agir sur quelle ressource | `peut_supprimer_document(utilisateur, document)` |
| Service de commande | Transition, invariants, transaction, journal | Valider une facture depuis son identifiant et sa révision |
| Requête de lecture | Chargement efficace du contexte d’un écran | Spectacles publiés avec affiches et prochaines dates |

Les vues reçoivent une requête, valident le formulaire, appellent ces fonctions et rendent un résultat. L’admin réutilise les mêmes transitions. La base complète ce dispositif avec les contraintes adaptées : unicité, cohérence simple des valeurs, intégrité des relations. Le fichier généré doit conserver l’audience et la version de la ressource dont il provient.

### Matrice de permissions à discuter

Cette matrice est une **proposition**, pas la description du comportement actuel. Une personne peut cumuler plusieurs rôles.

| Action | Membre | Programmation | Trésorerie | Secrétariat | Gestion des accès |
|---|---|---|---|---|---|
| Éditer ses projets | Oui, selon propriété et état | Idem ; édition élargie si mandat | Idem | Idem | Idem |
| Publier les projets proposés | Non | Oui | Non par défaut | Non par défaut | Non par défaut |
| Lire ses documents privés | Oui | Aucun accès supplémentaire | Aucun accès supplémentaire | Aucun accès supplémentaire | Aucun accès supplémentaire |
| Gérer les documents associatifs | Selon audience | Selon mandat | Pièces financières | Pièces administratives | Selon mandat explicite |
| Émettre factures/reçus | Non | Non | Oui | Non par défaut | Non par défaut |
| Organiser AG/PV | Répondre à sa convocation | Non par défaut | Non par défaut | Oui | Non par défaut |
| Attribuer les rôles | Non | Non | Non | Non | Oui, avec traçabilité |

Le compte technique superadministrateur doit être une exception assumée. Une étiquette « privé » dans l’application décrit une politique applicative ; elle ne signifie pas chiffrement de bout en bout face à l’administrateur du serveur.

## 10. Plan de travail priorisé

Estimations indicatives pour une personne connaissant Django et le dépôt, incluant tests ciblés et revue. Ce sont des ordres de grandeur techniques, pas des engagements de délai. Les reprises de données réelles peuvent augmenter l’effort.

| Lot | Contenu | Effort indicatif | Critère de sortie |
|---|---|---|---|
| 1 — Fermer les accès indus | SEC-01, SEC-02, contrôle des PV existants | 1–3 jours | Comptes atypiques et documents dérivés correctement isolés |
| 2 — Sécuriser les émissions | FIN-01, FIN-02, FIN-03, validation des lignes | 4–8 jours | Une émission unique, données figées, admin cohérent, concurrence PostgreSQL testée |
| 3 — Sécuriser l’exploitation | CI PostgreSQL, branches, locks de dépendances, sauvegarde et restauration | 3–6 jours | Aucun SHA non validé déployé ; restauration démontrée |
| 4 — Durcir les comptes et documents | Limitation des tentatives, MFA, audit, corbeille, versionnement | 4–8 jours | Attribution de droits et opérations sensibles traçables/récupérables |
| 5 — Fiabiliser les parcours front | Arrondis, erreurs, sauvegarde avant validation, thèmes, calendrier | 2–4 jours | Formulaires explicites et cohérents, aucun 500 sur entrées invalides |
| 6 — Valoriser les créations | Pages spectacles, aperçu auteur, collaboration, optimisation images | 3–6 jours | Publier/mettre à jour une fiche devient autonome et compréhensible |
| 7 — Consolider la gouvernance | Registre électoral, snapshots, clôture, pouvoirs | 2–5 jours | Résultats reproductibles et indépendants des réglages ultérieurs |

L’ordre peut être adapté : les petits correctifs front peuvent accompagner le lot 1, tandis que la facturation doit rester bloquée à l’usage sensible tant que ses garanties centrales ne sont pas établies. Si la gouvernance sert déjà à des décisions réelles, avancer le lot 7.

### Les cinq décisions métier nécessaires

1. Qui peut accorder les accès au bureau, et quelles responsabilités doivent être séparées ?
2. Quels droits un ancien membre conserve-t-il, et qui reprend ses projets ?
3. Les modifications des projets publiés restent-elles immédiatement visibles avec contrôle a posteriori ? Le code dit actuellement oui.
4. Le budget est-il un outil de pilotage de trésorerie ou doit-il couvrir des fonctions comptables plus formelles ?
5. Quels documents de réunion sont destinés au bureau, aux membres ou au public, et à partir de quel moment ?

Ces décisions n’empêchent pas de corriger dès maintenant les défauts d’autorisation et de concurrence confirmés.

## 11. Tests à ajouter en priorité

| Domaine | Scénarios manquants ou à renforcer |
|---|---|
| Identités | Anonyme ; compte sans fiche ; membre ; ancien membre ; bureau sans fiche ; staff limité ; superadmin |
| Documents | Chaque opération × propriétaire/audience/espace ; anciennes versions ; PV dérivés ; fichier sans dossier |
| Factures | Deux requêtes sur la même facture ; édition pendant validation ; première émission de l’année ; échec PDF ; changement de client après émission ; admin |
| Devis et avoirs | Double transformation ; suppression du dernier numéro ; répétition d’un avoir ; reprise après erreur |
| Réservations | Deux personnes pour la dernière place ; événement fermé/passé ; annulation ; répétition abusive |
| Gouvernance | Électorat complet ; paramètres modifiés après clôture ; pouvoirs concurrents ; différence bureau/membre |
| Front | Erreurs sur tous les champs ; totaux identiques ; modifications non sauvegardées ; JS absent ; navigation clavier |
| Exploitation | Migration sur base vide et existante ; déploiement échoué ; deuxième push ; restauration base + fichiers |

Les tests de sécurité devraient vérifier le **résultat concret** : refus HTTP, absence de mutation, absence de fichier transmis, absence de numéro consommé. Les assertions de chaînes HTML et les tests de CSS sont utiles, mais ne remplacent pas des tests fonctionnels de navigateur pour les interactions.

## 12. Annexe : preuves locales reproductibles

### Résultats observés

| Cas | Résultat observé au commit audité |
|---|---|
| Compte sans fiche → suppression d’un dossier officiel vide via route membre | 302 ; dossier supprimé |
| Compte sans fiche → suppression d’un document officiel via route membre | 302 ; ligne et fichier physique supprimés |
| Membre ordinaire → téléchargement du PV d’une réunion de bureau généré | 200 ; document classé `membres` |
| Deux instances du même brouillon → deux validations | `F2026-0001`, puis `F2026-0002` ; une facture, compteur 2 |
| Client modifié après validation, avant premier PDF | Nouveau nom présent dans le HTML destiné au PDF |
| Admin sur facture validée | Modification et suppression permises au superadmin ; client et statut éditables |
| Deux instances d’un devis → deux transformations | Deux factures liées au même devis |
| Deux remplacements de la même ancienne version | Deux successeurs v2, tous deux courants |
| Année 0 dans l’agenda calendrier | HTTP 500 |
| Huit spectacles avec affiche | Neuf requêtes SQL pour la page de liste locale |
| Quantité invalide dans une ligne de facture | Formulaire invalide ; message d’erreur absent du fragment HTML |
| Trois lignes 0,33 × 0,05 €, TVA 0 | Serveur 0,06 € ; calcul JS avant formatage 0,0495 € |

### Exemple minimal : renumérotation d’une même facture

À exécuter uniquement dans une base de test jetable après migration, avec les settings de test du projet. Le scénario ne nécessite pas de concurrence réelle pour révéler l’état périmé ; il ne remplace pas le futur test PostgreSQL simultané.

```python
from datetime import date
from apps.facturation.models import Client, Facture, LigneFacture
from apps.facturation.services import valider_facture

client = Client.objects.create(nom="Client de test")
facture = Facture.objects.create(client=client)
LigneFacture.objects.create(
    facture=facture, designation="Test", prix_unitaire_ht="150.00"
)
a = Facture.objects.get(pk=facture.pk)
b = Facture.objects.get(pk=facture.pk)

valider_facture(a, date_emission=date(2026, 9, 11))
premier_numero = a.numero
valider_facture(b, date_emission=date(2026, 9, 11))
facture.refresh_from_db()
assert facture.numero != premier_numero  # Défaut observé dans cette révision.
```

Le test de non-régression à intégrer après correction doit inverser la garantie attendue : la pièce garde son numéro, le compteur n’augmente qu’une fois et le second appel est traité sans nouvelle émission.

### Principe de correction du filtre de suppression

Exemple indicatif, à intégrer avec les tests, la politique de suppression et la future corbeille :

```python
membre = getattr(request.user, "membre", None)
if membre is None:
    raise Http404

document = get_object_or_404(
    Document,
    pk=pk,
    dossier__espace=Dossier.Espace.PERSO,
    dossier__proprietaire=membre,
)
```

Cette correction ferme le cas `NULL` ; elle n’apporte pas, à elle seule, journalisation, restauration ou atomicité entre base et fichiers.

## 13. Références techniques externes

Ces sources primaires précisent les mécanismes utilisés dans les recommandations. Les défauts propres à Improliante sont établis par le code et les reproductions décrites plus haut.

- **[S1] Django 6 — QuerySet / `select_for_update`** : verrouillage de lignes et limites sur SQLite. [Documentation](https://docs.djangoproject.com/en/6.0/ref/models/querysets/#select-for-update).
- **[S2] Django 6 — Sécurité** : protections du framework, limites de validation des fichiers téléversés et absence de limitation native des tentatives d’authentification. [Documentation](https://docs.djangoproject.com/en/6.0/topics/security/).
- **[S3] Django 6 — Content Security Policy** : middleware et configuration CSP native. [Documentation](https://docs.djangoproject.com/en/6.0/ref/csp/).
- **[S4] Django 6 — Installation** : versions Python compatibles. [Documentation](https://docs.djangoproject.com/en/6.0/faq/install/).
- **[S5] OWASP — Authorization Cheat Sheet** : refus par défaut et contrôle de chaque requête. [Référence](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

**Orientation recommandée :** conserver le socle et la richesse métier ; fermer les accès indus ; garantir l’intégrité des pièces émises ; sécuriser livraison et restauration ; puis améliorer les parcours de contribution et les pages publiques. La valeur d’Improliante réside dans sa correspondance avec la vie de l’association. La prochaine étape doit rendre cette correspondance fiable, vérifiable et facile à maintenir.
