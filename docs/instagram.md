# Flux Instagram de l'association

Affiche les derniers posts du **compte Instagram de l'association** (pas ceux des
membres) dans une section « Suivez-nous sur Instagram » sur l'accueil.

- **Rendu côté serveur** : Django appelle l'API de Meta avec un **jeton secret** ;
  ce jeton **ne part jamais au navigateur**.
- **Optionnel et dégradé** : si `INSTAGRAM_TOKEN` est vide, aucune section ne
  s'affiche (aucune erreur). Le résultat est mis en cache (`INSTAGRAM_CACHE_TTL`,
  30 min par défaut) pour ménager les quotas.
- **Membres** : inchangé — un simple lien Instagram sur leur fiche (pas de flux ;
  Instagram ne permet pas un flux « à partir du @ » sans authentification).

## Pré-requis (à faire une fois, côté Meta)

Instagram exige un **compte professionnel** (Business ou Creator) et une **app
Meta**. Les écrans Meta changent souvent — se référer à la doc officielle
« Instagram Platform » ; principe général :

1. Convertir le compte Instagram de l'asso en **compte professionnel**
   (Réglages Instagram → type de compte).
2. Créer une **app** sur <https://developers.facebook.com/> (type *Business*),
   y ajouter le produit **« Instagram »**.
3. Générer un **jeton d'accès longue durée** (« Instagram API with Instagram
   Login » — jeton valable ~60 jours, **à rafraîchir**) avec au moins la
   permission `instagram_business_basic` (lecture des médias).
4. Récupérer l'**identifiant du compte** (IG user id) — ou garder `me` selon le
   type de jeton.

> ⚠️ Le jeton **expire** (~60 jours). Prévoir un rafraîchissement périodique
> (tâche planifiée appelant l'endpoint `refresh_access_token`), sinon le flux
> s'éteindra silencieusement (dégradation) jusqu'au renouvellement.

## Configuration

Renseigner dans `.env` (dev) ou l'`EnvironmentFile` systemd (prod) :

```bash
INSTAGRAM_TOKEN=EAAG...            # le jeton longue durée (SECRET)
INSTAGRAM_USER_ID=me               # ou l'IG user id numérique
INSTAGRAM_API_BASE=https://graph.instagram.com   # ou graph.facebook.com selon le montage
INSTAGRAM_CACHE_TTL=1800           # cache en secondes (optionnel)
INSTAGRAM_TIMEOUT=5                # timeout réseau en secondes (optionnel)
```

Le service interroge `GET {API_BASE}/{USER_ID}/media` avec les champs
`id,caption,media_type,media_url,permalink,thumbnail_url,timestamp`
(cf. `apps/common/instagram.py`). Si le montage utilise un autre endpoint,
ajuster `INSTAGRAM_API_BASE` / `INSTAGRAM_USER_ID`.

## Vie privée (RGPD)

- Le **jeton** et l'appel à Meta restent **côté serveur** : le navigateur du
  visiteur ne parle qu'au serveur de l'asso.
- En revanche, les **vignettes** pointent vers le CDN d'Instagram
  (`img referrerpolicy="no-referrer"` pour limiter la fuite de référent) : les
  charger expose l'IP du visiteur à Meta. Si tu veux une conformité stricte, deux
  pistes simples à ajouter ensuite : **proxifier/cacher les images** côté serveur,
  ou passer la section en **chargement au clic** (consentement), comme le widget
  Bluesky des fiches membres.
- Si la **CSP** (`django-csp`) est activée un jour, autoriser le CDN Instagram
  dans `img-src` (ex. `scontent.cdninstagram.com`). L'appel API étant serveur,
  `connect-src` n'est pas concerné.
