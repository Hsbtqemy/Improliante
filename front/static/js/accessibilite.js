/* Panneau d'accessibilité : bascule des options d'affichage.
 *
 * Les préférences sont stockées dans le cookie « a11y » (liste de classes
 * séparées par des espaces). Le serveur applique déjà ces classes sur <html>
 * au chargement (pas de FOUC) ; ce script les met à jour et réécrit le cookie.
 */
(function () {
  "use strict";

  var html = document.documentElement;
  var bouton = document.getElementById("a11y-bouton");
  var panneau = document.getElementById("a11y-panneau");
  if (!bouton || !panneau) {
    return;
  }

  function classesActuelles() {
    return (html.getAttribute("class") || "").split(/\s+/).filter(Boolean);
  }

  function enregistrer(liste) {
    html.setAttribute("class", liste.join(" "));
    document.cookie =
      "a11y=" + liste.join(" ") + "; path=/; max-age=31536000; samesite=Lax";
    majEtats();
  }

  function basculer(classe) {
    var liste = classesActuelles();
    var index = liste.indexOf(classe);
    if (index >= 0) {
      liste.splice(index, 1);
    } else {
      liste.push(classe);
    }
    enregistrer(liste);
  }

  function cyclerTexte() {
    var actuelles = classesActuelles();
    var etaitGrand = actuelles.indexOf("txt-grand") >= 0;
    var etaitMax = actuelles.indexOf("txt-max") >= 0;
    var liste = actuelles.filter(function (c) {
      return c !== "txt-grand" && c !== "txt-max";
    });
    if (etaitGrand) {
      liste.push("txt-max");
    } else if (!etaitMax) {
      liste.push("txt-grand");
    }
    // (si txt-max : on revient à la taille normale)
    enregistrer(liste);
  }

  function reinitialiser() {
    enregistrer([]);
  }

  function majEtats() {
    var liste = classesActuelles();
    panneau.querySelectorAll("[data-a11y-toggle]").forEach(function (btn) {
      var actif = liste.indexOf(btn.getAttribute("data-a11y-toggle")) >= 0;
      btn.setAttribute("aria-pressed", actif ? "true" : "false");
    });
  }

  function ouvrir() {
    panneau.hidden = false;
    bouton.setAttribute("aria-expanded", "true");
    var premier = panneau.querySelector("button");
    if (premier) {
      premier.focus();
    }
  }

  function fermer() {
    panneau.hidden = true;
    bouton.setAttribute("aria-expanded", "false");
    bouton.focus();
  }

  bouton.addEventListener("click", function () {
    if (panneau.hidden) {
      ouvrir();
    } else {
      fermer();
    }
  });

  panneau.querySelector(".a11y__fermer").addEventListener("click", fermer);
  panneau.querySelector(".a11y__reset").addEventListener("click", reinitialiser);

  var boutonTexte = panneau.querySelector("[data-a11y-cycle-texte]");
  if (boutonTexte) {
    boutonTexte.addEventListener("click", cyclerTexte);
  }

  panneau.querySelectorAll("[data-a11y-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      basculer(btn.getAttribute("data-a11y-toggle"));
    });
  });

  // Éléments focusables du panneau (pour le piège de focus du dialogue modal).
  function focusables() {
    return Array.prototype.slice
      .call(panneau.querySelectorAll("button, [href], input, select, [tabindex]"))
      .filter(function (el) {
        return !el.disabled && el.tabIndex !== -1 && el.offsetParent !== null;
      });
  }

  document.addEventListener("keydown", function (event) {
    if (panneau.hidden) {
      return;
    }
    if (event.key === "Escape") {
      fermer();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    // Piège de focus : tant que le dialogue (aria-modal) est ouvert, la
    // tabulation boucle à l'intérieur du panneau au lieu d'en sortir.
    var liste = focusables();
    if (!liste.length) {
      return;
    }
    var premier = liste[0];
    var dernier = liste[liste.length - 1];
    if (event.shiftKey && document.activeElement === premier) {
      dernier.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === dernier) {
      premier.focus();
      event.preventDefault();
    }
  });

  majEtats();
})();
