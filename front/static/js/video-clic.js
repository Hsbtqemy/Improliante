// Lecteur vidéo AU CLIC sur la fiche artiste (RGPD).
//
// Tant que le visiteur n'a pas cliqué, la page ne demande RIEN à YouTube : pas
// de cadre, pas de vignette, pas de préconnexion. Au clic, on remplace le lien
// par un cadre servi depuis le domaine sans cookie de YouTube.
//
// Sans JavaScript, le lien reste un lien et ouvre la vidéo chez YouTube : le
// geste n'est jamais mort, il est seulement moins confortable.
(function () {
  "use strict";

  var FOURNISSEUR = "https://www.youtube-nocookie.com/embed/";
  var IDENTIFIANT = /^[A-Za-z0-9_-]{11}$/;

  function ouvrir(section, facade) {
    var id = section.getAttribute("data-video-youtube") || "";
    // On revérifie ici ce que le serveur a déjà validé. Ce n'est pas de la
    // méfiance envers le serveur : c'est que cette fonction construit une `src`
    // à partir d'un attribut du document, et qu'une `src` ne se construit jamais
    // à partir d'une valeur qu'on n'a pas regardée.
    if (!IDENTIFIANT.test(id)) {
      return false;
    }
    var cadre = document.createElement("iframe");
    cadre.className = "video-clic__cadre";
    cadre.src = FOURNISSEUR + id + "?autoplay=1";
    cadre.title = (facade.textContent || "Vidéo").trim();
    cadre.setAttribute(
      "allow",
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    );
    cadre.setAttribute("allowfullscreen", "");
    cadre.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    facade.replaceWith(cadre);
    // Le lien cliqué n'existe plus : sans ce rappel, le focus retombe sur
    // <body> et la navigation au clavier repart du haut de la page.
    cadre.setAttribute("tabindex", "-1");
    cadre.focus();
    return true;
  }

  var sections = document.querySelectorAll(".video-clic[data-video-youtube]");
  Array.prototype.forEach.call(sections, function (section) {
    var facade = section.querySelector(".video-clic__facade");
    if (!facade) {
      return;
    }
    facade.addEventListener("click", function (evenement) {
      // Si l'identifiant ne convainc pas, on ne bloque pas le lien : le visiteur
      // part chez YouTube plutôt que de cliquer dans le vide.
      if (ouvrir(section, facade)) {
        evenement.preventDefault();
      }
    });
  });
})();
