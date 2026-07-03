// Lignes de facture / devis : ajout dynamique, suppression, total en direct.
//
// Amélioration progressive : sans JS, une ligne vide est disponible et la
// suppression se fait par la case « Retirer » (DELETE). Avec JS : bouton
// « + Ajouter une ligne » (clone de `empty_form`), bouton ✕ par ligne (barre la
// ligne + la marque pour suppression), et total HT/TVA/TTC recalculé à la saisie.
(function () {
  "use strict";

  function nombre(v) {
    var n = parseFloat(String(v == null ? "" : v).replace(",", "."));
    return isNaN(n) ? 0 : n;
  }

  function euros(n) {
    return (
      n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €"
    );
  }

  function valeur(tr, suffixe) {
    var el = tr.querySelector('[name$="-' + suffixe + '"]');
    return el ? el.value : "";
  }

  function activer(conteneur) {
    var prefixe = conteneur.getAttribute("data-formset-lignes");
    var tbody = conteneur.querySelector("tbody");
    var totalForms = document.getElementById("id_" + prefixe + "-TOTAL_FORMS");
    var gabarit = conteneur.querySelector("[data-empty-form]");
    var btnAjouter = conteneur.querySelector("[data-ajouter-ligne]");
    var celluleHt = conteneur.querySelector("[data-total-ht]");
    var celluleTva = conteneur.querySelector("[data-total-tva]");
    var celluleTtc = conteneur.querySelector("[data-total-ttc]");
    if (!tbody || !totalForms) {
      return;
    }

    function recalculer() {
      var ht = 0;
      var tva = 0;
      tbody.querySelectorAll("tr").forEach(function (tr) {
        var del = tr.querySelector('input[type="checkbox"][name$="-DELETE"]');
        var supprimee = !!(del && del.checked);
        tr.classList.toggle("ligne-facturation--supprimee", supprimee);
        if (supprimee) {
          return;
        }
        var ligneHt = nombre(valeur(tr, "quantite")) * nombre(valeur(tr, "prix_unitaire_ht"));
        ht += ligneHt;
        tva += (ligneHt * nombre(valeur(tr, "taux_tva"))) / 100;
      });
      if (celluleHt) {
        celluleHt.textContent = euros(ht);
      }
      if (celluleTva) {
        celluleTva.textContent = euros(tva);
      }
      if (celluleTtc) {
        celluleTtc.textContent = euros(ht + tva);
      }
    }

    function preparerLigne(tr) {
      var del = tr.querySelector('input[type="checkbox"][name$="-DELETE"]');
      var bouton = tr.querySelector("[data-supprimer-ligne]");
      var label = tr.querySelector(".ligne-facturation__del");
      if (!del || !bouton) {
        return;
      }
      if (label) {
        label.hidden = true; // JS actif : on masque la case brute
      }
      bouton.hidden = false;
      bouton.addEventListener("click", function () {
        del.checked = !del.checked;
        bouton.setAttribute("aria-pressed", String(del.checked));
        recalculer();
      });
    }

    function ajouterLigne() {
      var index = parseInt(totalForms.value, 10) || 0;
      var html = gabarit.textContent.replace(/__prefix__/g, index).trim();
      var tampon = document.createElement("tbody");
      tampon.innerHTML = html;
      var tr = tampon.querySelector("tr");
      if (!tr) {
        return;
      }
      tbody.appendChild(tr);
      totalForms.value = index + 1;
      preparerLigne(tr);
      recalculer();
      var premier = tr.querySelector('input:not([type="hidden"]), select, textarea');
      if (premier) {
        premier.focus();
      }
    }

    // Délégation : couvre aussi les lignes ajoutées après coup.
    tbody.addEventListener("input", recalculer);
    tbody.addEventListener("change", recalculer);
    if (btnAjouter && gabarit) {
      btnAjouter.addEventListener("click", ajouterLigne);
    }
    tbody.querySelectorAll("tr").forEach(preparerLigne);
    recalculer();
  }

  document.querySelectorAll("[data-formset-lignes]").forEach(activer);
})();
