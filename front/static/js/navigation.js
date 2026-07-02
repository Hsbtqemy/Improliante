// Bascule mobile de la navigation de l'espace connecté (sidebar).
//
// Amélioration progressive : sans JS, le bouton reste masqué (attribut `hidden`
// posé dans le gabarit) et la navigation s'affiche normalement — donc utilisable
// sans script. Avec JS, sur petit écran, la navigation est repliée par défaut et
// pilotée par un bouton (aria-expanded). Sur grand écran, elle est toujours
// visible et le bouton reste masqué.
(function () {
  "use strict";

  var bouton = document.querySelector("[data-bascule-nav]");
  var nav = document.getElementById("nav-espace");
  if (!bouton || !nav) {
    return;
  }

  var petitEcran = window.matchMedia("(max-width: 47.999rem)");

  function synchroniser() {
    if (petitEcran.matches) {
      // Mobile : bouton actif, navigation repliée par défaut.
      bouton.hidden = false;
      bouton.setAttribute("aria-expanded", "false");
      nav.hidden = true;
    } else {
      // Desktop : navigation toujours visible, bouton masqué.
      bouton.hidden = true;
      bouton.setAttribute("aria-expanded", "true");
      nav.hidden = false;
    }
  }

  bouton.addEventListener("click", function () {
    var ouvert = bouton.getAttribute("aria-expanded") === "true";
    bouton.setAttribute("aria-expanded", String(!ouvert));
    nav.hidden = ouvert;
  });

  // matchMedia : addEventListener('change') moderne, addListener en repli.
  if (petitEcran.addEventListener) {
    petitEcran.addEventListener("change", synchroniser);
  } else if (petitEcran.addListener) {
    petitEcran.addListener(synchroniser);
  }

  synchroniser();
})();
