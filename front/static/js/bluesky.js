// Encart Bluesky sur la fiche membre — chargement AU CLIC (RGPD).
//
// Aucune requête vers Bluesky tant que l'internaute n'a pas cliqué. Au clic, on
// interroge l'API PUBLIQUE de Bluesky (pas de clé, pas de cookie, pas de script
// tiers) pour récupérer les derniers posts du handle, et on les rend nous-mêmes.
// Le texte des posts est inséré via textContent (jamais innerHTML) : pas
// d'injection possible depuis le contenu distant.
(function () {
  "use strict";

  var API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed";
  var LIMITE = 5;

  function dateCourte(iso) {
    if (!iso) {
      return "";
    }
    var d = new Date(iso);
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString("fr-FR");
  }

  function lienPost(handle, post) {
    var rkey = (post.uri || "").split("/").pop();
    return (
      "https://bsky.app/profile/" +
      encodeURIComponent(handle) +
      "/post/" +
      encodeURIComponent(rkey)
    );
  }

  function rendre(section, handle, cible, feed) {
    if (!feed.length) {
      cible.textContent = "Aucun post récent.";
      return;
    }
    var liste = document.createElement("ul");
    liste.className = "bluesky-feed__liste";
    feed.slice(0, LIMITE).forEach(function (item) {
      var post = item && item.post;
      if (!post || !post.record) {
        return;
      }
      var li = document.createElement("li");
      li.className = "bluesky-feed__post";

      var texte = document.createElement("p");
      texte.className = "bluesky-feed__texte";
      texte.textContent = post.record.text || "";
      li.appendChild(texte);

      var lien = document.createElement("a");
      lien.href = lienPost(handle, post);
      lien.target = "_blank";
      lien.rel = "noopener nofollow";
      var quand = dateCourte(post.record.createdAt);
      lien.textContent = (quand ? quand + " · " : "") + "voir sur Bluesky";
      li.appendChild(lien);

      liste.appendChild(li);
    });
    cible.appendChild(liste);
  }

  function activer(section) {
    var handle = section.getAttribute("data-bluesky-handle");
    var bouton = section.querySelector("[data-bluesky-charger]");
    var cible = section.querySelector(".bluesky-feed__posts");
    if (!handle || !bouton || !cible) {
      return;
    }

    bouton.addEventListener("click", function () {
      bouton.disabled = true;
      bouton.textContent = "Chargement…";
      var url =
        API +
        "?actor=" +
        encodeURIComponent(handle) +
        "&limit=" +
        LIMITE +
        "&filter=posts_no_replies";

      fetch(url)
        .then(function (r) {
          if (!r.ok) {
            throw new Error("HTTP " + r.status);
          }
          return r.json();
        })
        .then(function (data) {
          bouton.hidden = true;
          rendre(section, handle, cible, (data && data.feed) || []);
        })
        .catch(function () {
          bouton.hidden = true;
          cible.textContent = "Impossible de charger les posts pour le moment.";
        });
    });
  }

  document.querySelectorAll("[data-bluesky-handle]").forEach(activer);
})();
