// Création d'un client à la volée depuis le devis / la facture.
//
// Ajoute une option « ➕ Ajouter un nouveau client… » au menu déroulant client.
// Quand elle est choisie, révèle le fieldset « Nouveau client » (et l'active
// pour que ses champs soient soumis). Amélioration progressive : sans JS,
// l'option n'existe pas et le fieldset reste `hidden disabled` — on utilise
// alors l'écran Clients dédié. Le serveur crée le client dans la même
// transaction que le devis/facture (annulé si le reste est invalide).
(function () {
  "use strict";

  var VALEUR = "__nouveau__";
  var select = document.getElementById("id_client");
  var fieldset = document.getElementById("nouveau-client");
  if (!select || !fieldset) {
    return;
  }

  if (!select.querySelector('option[value="' + VALEUR + '"]')) {
    var option = document.createElement("option");
    option.value = VALEUR;
    option.textContent = "➕ Ajouter un nouveau client…";
    select.appendChild(option);
  }

  function synchroniser(focus) {
    var actif = select.value === VALEUR;
    fieldset.hidden = !actif;
    fieldset.disabled = !actif; // désactivé => champs non soumis quand inactif
    if (actif && focus) {
      var premier = fieldset.querySelector("input, textarea, select");
      if (premier) {
        premier.focus();
      }
    }
  }

  select.addEventListener("change", function () {
    synchroniser(true);
  });

  // Après un POST invalide avec « nouveau client » : ré-ouvrir le fieldset.
  if (fieldset.dataset.ouvert === "1") {
    select.value = VALEUR;
  }
  synchroniser(false);
})();
