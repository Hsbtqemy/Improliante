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

  // Groupes repliables de la nav de l'espace (<details>). Sur petit écran, seul
  // le groupe de la page courante reste ouvert (le reste est replié pour tenir
  // dans le tiroir). Sur grand écran, tous les groupes sont dépliés (rail
  // latéral). Sans JS, tous restent ouverts (attribut `open` du gabarit).
  function gererGroupes() {
    var groupes = document.querySelectorAll(
      "#nav-espace details.nav-espace__groupe"
    );
    if (!groupes.length) {
      return;
    }

    // Desktop : le rail reste toujours déplié. Le CSS neutralise la souris
    // (pointer-events), mais pas le clavier (Entrée sur le summary) : on bloque
    // donc le repli ici. En mobile, le repli fonctionne normalement.
    groupes.forEach(function (details) {
      var resume = details.querySelector("summary");
      if (resume) {
        resume.addEventListener("click", function (evenement) {
          if (!petitEcran.matches) {
            evenement.preventDefault();
          }
        });
      }
    });

    function synchroniser() {
      groupes.forEach(function (details) {
        if (petitEcran.matches) {
          details.open = !!details.querySelector('[aria-current="page"]');
        } else {
          details.open = true;
        }
      });
    }

    if (petitEcran.addEventListener) {
      petitEcran.addEventListener("change", synchroniser);
    } else if (petitEcran.addListener) {
      petitEcran.addListener(synchroniser);
    }

    synchroniser();
  }

  gererGroupes();
})();
