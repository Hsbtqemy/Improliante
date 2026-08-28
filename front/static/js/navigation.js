// Bascule mobile (menu burger) des navigations : en-tête public ET sidebar de
// l'espace connecté. Chaque bouton `[data-bascule-nav]` pilote l'élément désigné
// par son `aria-controls`.
//
// Amélioration progressive : sans JS, le bouton reste masqué (attribut `hidden`
// posé dans le gabarit) et la navigation s'affiche normalement — donc utilisable
// sans script. Avec JS, sur petit écran, la navigation est repliée par défaut et
// pilotée par le bouton (aria-expanded). Sur grand écran, elle est toujours
// visible et le bouton reste masqué.
(function () {
  "use strict";

  var petitEcran = window.matchMedia("(max-width: 47.999rem)");

  function activer(bouton) {
    var cible = document.getElementById(bouton.getAttribute("aria-controls"));
    if (!cible) {
      return;
    }

    function synchroniser() {
      if (petitEcran.matches) {
        // Mobile : bouton actif, navigation repliée par défaut.
        bouton.hidden = false;
        bouton.setAttribute("aria-expanded", "false");
        cible.hidden = true;
      } else {
        // Desktop : navigation toujours visible, bouton masqué.
        bouton.hidden = true;
        bouton.setAttribute("aria-expanded", "true");
        cible.hidden = false;
      }
    }

    bouton.addEventListener("click", function () {
      var ouvert = bouton.getAttribute("aria-expanded") === "true";
      bouton.setAttribute("aria-expanded", String(!ouvert));
      cible.hidden = ouvert;
    });

    // matchMedia : addEventListener('change') moderne, addListener en repli.
    if (petitEcran.addEventListener) {
      petitEcran.addEventListener("change", synchroniser);
    } else if (petitEcran.addListener) {
      petitEcran.addListener(synchroniser);
    }

    synchroniser();
  }

  document.querySelectorAll("[data-bascule-nav]").forEach(activer);

  // Groupes repliables de la nav de l'espace (<details>). Seul le groupe de la
  // page courante reste ouvert — en mobile comme en desktop. Le rail comptait
  // 19 entrées dépliées en permanence pour un membre du bureau, dont la
  // dernière tombait 406 px sous le pli d'un portable : il fallait faire
  // défiler la page pour atteindre « Paramètres ». Sans JS, tous les groupes
  // restent ouverts (attribut `open` du gabarit) : rien n'est inatteignable.
  function gererGroupes() {
    var groupes = document.querySelectorAll(
      "#nav-espace details.nav-espace__groupe"
    );
    if (!groupes.length) {
      return;
    }

    var courant = null;
    groupes.forEach(function (details) {
      if (details.querySelector('[aria-current="page"]')) {
        courant = details;
      }
    });
    // Écran atteint sans entrée de rail correspondante (formulaire profond,
    // fiche de détail) : ouvrir le premier groupe utile plutôt qu'un rail muet.
    if (!courant) {
      courant = document.querySelector(
        "#nav-espace details.nav-espace__groupe:not(.nav-espace__groupe--site)"
      );
    }
    groupes.forEach(function (details) {
      details.open = details === courant;
    });
  }

  gererGroupes();
})();
