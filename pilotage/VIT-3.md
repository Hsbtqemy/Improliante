---
chantier: VIT-3
statut: interrompu
---

# VIT-3 — identité visuelle de la vitrine : palette, fond, titres

**Arrêté sur** — sélecteur de police de titre ajouté au panneau DEV, quatre
candidates auto-hébergées, commit `7b37df3`, 28 août 2026.

## Reste

### Arbitrages
- [ ] Arrêter la palette parmi les douze du sélecteur (A bordeaux … L encre neutre)
- [ ] Arrêter le fond parmi les trois (plat teinté, mesh animé, grain)
- [ ] Arrêter la police de titre parmi les cinq (système, Fraunces, Playfair, Instrument, Bricolage)

### Retrait du panneau DEV
- [ ] Supprimer le bloc `.theme-switch` et son script de `base.html`, une fois les trois choix faits
- [ ] Figer les trois choix dans `:root` et retirer les attributs `data-theme` / `data-fond` / `data-titre` de `<html>`
- [ ] Purger le CSS des onze palettes et des deux fonds écartés, et supprimer leurs blocs `html[data-theme=…]`
- [ ] Ne garder que le `.woff2` retenu dans `front/static/fonts/` ; supprimer les trois autres et leurs `@font-face`

### Mise en production de la fonte
- [ ] Sous-régler la fonte retenue sur le latin utilisé par le site, et vérifier que le fichier reste sous 30 ko
- [ ] Précharger la fonte (`<link rel="preload" as="font" crossorigin>`) dans `base.html`
- [ ] Calculer `size-adjust` / `ascent-override` sur la police de repli et vérifier au DevTools que le CLS des pages à gros titre reste à 0

### Vérifications
- [ ] Contrôler le rendu des titres longs sur 375 px (« Politique de confidentialité », titres de spectacles)
- [ ] Vérifier le contraste AA des titres sur la palette retenue, la fonte retenue en place
- [ ] Regarder les douze palettes en mode sombre (`html.sombre`) : le test ne couvre que le mode clair

## Contexte

**Décision du 28 août 2026** : le panneau DEV reste en place tant que les trois
choix ne sont pas arrêtés. Il n'est donc **pas** conditionné à `settings.DEBUG` —
il sera retiré d'un bloc, avec les variantes écartées, quand les choix seront
faits. C'est le geste que décrit la zone « Retrait du panneau DEV » ci-dessus.

Conséquence à ne pas perdre de vue : en l'état, le panneau est servi à **tous les
visiteurs**. Il doit donc disparaître avant DEP-1, et cette fiche est ce qui le
garantit — aucun garde technique ne le fera à notre place.

Le défaut de départ, côté typographie : `--police-titre` et la pile du corps
résolvaient vers la **même fonte** sur toutes les plateformes (macOS et Android
ignorent « Segoe UI » et tombent sur system-ui ; sur Windows, system-ui *est*
Segoe UI). Il n'y avait pas de police de titre, seulement la police d'interface
en gras 800 — ce qui explique que les titres aient paru « pas adaptés ».

Auto-hébergement des fontes décidé et non négociable : servir depuis
fonts.gstatic.com transmet l'IP des visiteurs à Google, ce que la CNIL sanctionne
pour un site français. Les quatre `.woff2` sont versionnés dans
`front/static/fonts/`.

La police de titre pilote aussi `.site-logo` : changer de fonte change le logo
« L'Improliante » en même temps que les titres. C'est voulu, mais c'est à
regarder au moment du choix.

Le contraste AA des palettes n'est plus une intention : `apps/vitrine/tests.py
::test_les_palettes_respectent_le_contraste_AA` mesure dix paires réellement
peintes sur chaque palette présente dans le CSS, palettes futures comprises. Il a
révélé deux défauts sur l'existant (item du rail à 4,05 et 4,29 ; survol du bouton
principal en ambre codé en dur). **Limite connue** : il ne couvre que le mode
clair — le mode sombre (`html.sombre`) redéfinit canvas et surfaces et reste à
vérifier à la main.

Les trois choix ne sont pas indépendants : le contraste des titres se juge sur la
palette retenue, et le mesh animé change la lisibilité d'un titre à serif fine.
Les arrêter dans l'ordre palette → fond → titres évite de revenir en arrière.
