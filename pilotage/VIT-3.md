---
chantier: VIT-3
statut: interrompu
---

# VIT-3 — identité typographique de la vitrine

**Arrêté sur** — sélecteur de police de titre dans le panneau DEV, quatre
candidates auto-hébergées, commit `7b37df3`, 28 août 2026.

## Reste

### Arbitrages
- [ ] Arrêter la police de titre parmi les cinq du sélecteur (système, Fraunces, Playfair, Instrument, Bricolage)

### Mise en production
- [ ] Ne garder que le `.woff2` retenu dans `front/static/fonts/` ; supprimer les trois autres et leurs `@font-face`
- [ ] Retirer la rangée « Titres » du sélecteur DEV et figer `--police-titre` dans `:root`
- [ ] Sous-régler la fonte retenue sur le latin utilisé par le site, et vérifier que le fichier reste sous 30 ko
- [ ] Précharger la fonte (`<link rel="preload" as="font" crossorigin>`) dans `base.html`
- [ ] Calculer `size-adjust` / `ascent-override` sur la police de repli et vérifier au DevTools que le CLS des pages à gros titre reste à 0

### Vérifications
- [ ] Contrôler le rendu des titres longs sur 375 px (« Politique de confidentialité », titres de spectacles)
- [ ] Vérifier le contraste AA des titres sur les sept palettes du sélecteur, la fonte retenue en place

## Contexte

Le défaut de départ : `--police-titre` et la pile du corps résolvaient vers la
**même fonte** sur toutes les plateformes (macOS et Android ignorent « Segoe UI »
et tombent sur system-ui ; sur Windows system-ui *est* Segoe UI). Il n'y avait
donc pas de police de titre, seulement une police d'interface en gras 800 — ce
qui explique que les titres aient paru « pas adaptés ».

Le sélecteur est un outil de décision, pas une fonctionnalité : il vit dans le
même panneau DEV que Palette et Fond et doit disparaître avec lui.

Auto-hébergement décidé et non négociable : servir les fontes depuis
fonts.gstatic.com transmet l'IP des visiteurs à Google, ce que la CNIL
sanctionne pour un site français. Les quatre `.woff2` sont versionnés dans
`front/static/fonts/`.

La police de titre pilote aussi `.site-logo` : changer de fonte change le logo
« L'Improliante » en même temps que les titres. C'est voulu, mais c'est à
regarder au moment du choix.

Point à trancher au passage : le panneau DEV (Palette / Fond / Titres) est servi
à **tous les visiteurs**, y compris en production. Il devra être conditionné à
`settings.DEBUG` ou supprimé avant DEP-1.
