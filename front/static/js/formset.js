// Ajout / retrait dynamique de lignes d'un formset inline (intervenants,
// distribution). Amélioration progressive : sans JS, une ligne vide reste
// disponible (ajout par enregistrement) et la case « Retirer » supprime à
// l'enregistrement. Avec JS : « + Ajouter » clone `empty_form` (remplace
// `__prefix__`, incrémente TOTAL_FORMS) et chaque ligne reçoit un bouton « × »
// qui coche sa case DELETE et la masque — sans rechargement.
(function () {
  "use strict";

  // Dote une ligne d'un bouton « × » et masque la case DELETE native (qui reste
  // dans le DOM : c'est elle que coche le bouton pour la suppression côté serveur).
  function equiper(ligne) {
    if (ligne.hasAttribute("data-equipee")) {
      return;
    }
    ligne.setAttribute("data-equipee", "1");

    var champSuppr = ligne.querySelector("[data-formset-delete]");
    var caseSuppr = champSuppr ? champSuppr.querySelector('input[type="checkbox"]') : null;
    if (champSuppr) {
      champSuppr.hidden = true;
    }

    var bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "fiche-ligne__retirer";
    bouton.setAttribute("aria-label", "Retirer cette ligne");
    bouton.title = "Retirer";
    bouton.textContent = "×"; // ×
    bouton.addEventListener("click", function () {
      if (caseSuppr) {
        caseSuppr.checked = true;
        ligne.hidden = true;
      } else {
        ligne.parentNode.removeChild(ligne);
      }
    });
    ligne.appendChild(bouton);
  }

  function activer(conteneur) {
    var prefixe = conteneur.getAttribute("data-formset");
    var lignes = conteneur.querySelector("[data-formset-rows]");
    var totalForms = document.getElementById("id_" + prefixe + "-TOTAL_FORMS");
    var gabarit = conteneur.querySelector("[data-formset-empty]");
    var bouton = conteneur.querySelector("[data-formset-add]");
    if (!lignes || !totalForms || !gabarit || !bouton) {
      return;
    }

    lignes.querySelectorAll(".fiche-ligne").forEach(equiper);

    bouton.addEventListener("click", function () {
      var index = parseInt(totalForms.value, 10) || 0;
      var html = gabarit.textContent.replace(/__prefix__/g, index).trim();
      var tampon = document.createElement("ul");
      tampon.innerHTML = html;
      var ligne = tampon.querySelector("li");
      if (!ligne) {
        return;
      }
      lignes.appendChild(ligne);
      totalForms.value = index + 1;
      equiper(ligne);
      var premier = ligne.querySelector('select, input:not([type="hidden"]):not([type="checkbox"]), textarea');
      if (premier) {
        premier.focus();
      }
    });
  }

  document.querySelectorAll("[data-formset]").forEach(activer);
})();
