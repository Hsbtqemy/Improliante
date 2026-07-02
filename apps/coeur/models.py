"""Modèles du domaine « Cœur associatif » : identité et socle partagé.

- `Utilisateur` : modèle utilisateur du projet (AUTH_USER_MODEL). Identique au
  `User` de Django en v1, mais défini dès le départ pour rester extensible
  (login par e-mail, champs d'authentification, 2FA) sans migration lourde.
- `Membre` : profil associatif rattaché à un `Utilisateur` (OneToOne). Porte
  les informations propres à l'association et à la présentation publique.
- `Lieu` : lieu réutilisable (salles, théâtres) référencé par l'agenda.
"""

from __future__ import annotations

import base64
import mimetypes

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.stockage import StockagePrive


class Utilisateur(AbstractUser):
    """Utilisateur du projet — modèle d'authentification (AUTH_USER_MODEL).

    En v1, aucun champ n'est ajouté : on hérite tel quel d'`AbstractUser`. Le
    seul fait de le déclarer dès maintenant permet d'étendre l'authentification
    plus tard (e-mail comme identifiant, etc.) sans la migration délicate d'un
    changement de modèle utilisateur en cours de projet.
    """

    class Meta(AbstractUser.Meta):
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"


class Membre(models.Model):
    """Profil associatif d'une personne, rattaché à un compte `Utilisateur`.

    Tout `Utilisateur` n'est pas forcément un `Membre` (ex. compte technique) ;
    à l'inverse, l'espace membre s'appuie sur `request.user.membre` (règle
    anti-IDOR : toujours filtrer par le membre connecté).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membre",
        verbose_name="compte utilisateur",
    )
    telephone = models.CharField("téléphone", max_length=32, blank=True)
    role_public = models.CharField(
        "rôle public",
        max_length=200,
        blank=True,
        help_text="Ex. « Comédienne, mise en scène » — affiché sur la fiche publique.",
    )
    bio = models.TextField("biographie", blank=True)
    site_web = models.URLField("site web", blank=True)
    visible_sur_site = models.BooleanField(
        "visible sur le site public",
        default=False,
        help_text="La fiche n'apparaît sur le site public que si cette case est cochée.",
    )
    actif = models.BooleanField("membre actif", default=True)
    date_adhesion = models.DateField(
        "date d'entrée dans l'association",
        null=True,
        blank=True,
    )
    date_creation = models.DateTimeField("créé le", auto_now_add=True)
    date_modification = models.DateTimeField("modifié le", auto_now=True)

    photo = models.ForeignKey(
        "medias.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="photo",
        help_text="Portrait affiché sur la fiche publique (si le membre est visible).",
    )

    class Meta:
        verbose_name = "membre"
        verbose_name_plural = "membres"
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self) -> str:
        return self.user.get_full_name() or self.user.get_username()


class LienReseau(models.Model):
    """Lien vers un réseau social (ou autre) rattaché à un `Membre`.

    Liste flexible (0..n) plutôt que des champs fixes : on peut ajouter
    n'importe quel réseau, dans l'ordre voulu. Le `libelle` sert à nommer un
    lien « Autre » (sinon on affiche le libellé du réseau)."""

    class Reseau(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        YOUTUBE = "youtube", "YouTube"
        TIKTOK = "tiktok", "TikTok"
        LINKEDIN = "linkedin", "LinkedIn"
        BLUESKY = "bluesky", "Bluesky"
        MASTODON = "mastodon", "Mastodon"
        AUTRE = "autre", "Autre"

    membre = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.CASCADE,
        related_name="liens_reseaux",
        verbose_name="membre",
    )
    reseau = models.CharField("réseau", max_length=20, choices=Reseau.choices)
    url = models.URLField("adresse")
    libelle = models.CharField(
        "libellé",
        max_length=80,
        blank=True,
        help_text="Nom affiché si « Autre » (sinon le nom du réseau est utilisé).",
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "lien réseau social"
        verbose_name_plural = "liens réseaux sociaux"
        ordering = ["ordre", "id"]

    def __str__(self) -> str:
        return f"{self.libelle or self.get_reseau_display()} — {self.url}"

    @property
    def nom_affiche(self) -> str:
        """Libellé à afficher : le libellé libre s'il existe, sinon le réseau."""
        return self.libelle or self.get_reseau_display()


class ParametresAssociation(models.Model):
    """Identité légale de l'association (instance unique, éditable en admin).

    Sert d'en-tête aux documents officiels — d'abord les reçus fiscaux (Cerfa
    n° 11580), plus tard factures et courriers. Jamais codée en dur (règle 8).
    """

    nom = models.CharField(max_length=200, default="")
    objet = models.TextField(
        "objet de l'association",
        blank=True,
        help_text="Tel que déclaré (figure sur le reçu fiscal).",
    )
    adresse = models.CharField(max_length=255, blank=True)
    code_postal = models.CharField("code postal", max_length=16, blank=True)
    ville = models.CharField(max_length=120, blank=True)

    numero_rna = models.CharField("n° RNA", max_length=20, blank=True)
    numero_siret = models.CharField("SIRET", max_length=20, blank=True)

    # Fondement de la déduction fiscale (art. 200 / 238 bis du CGI selon le cas).
    article_cgi = models.CharField("article du CGI", max_length=20, default="200")

    signataire_nom = models.CharField("nom du signataire", max_length=200, blank=True)
    signataire_qualite = models.CharField(
        "qualité du signataire",
        max_length=120,
        blank=True,
        help_text="Ex. président·e, trésorier·e.",
    )

    class Meta:
        verbose_name = "paramètres de l'association"
        verbose_name_plural = "paramètres de l'association"

    def __str__(self) -> str:
        return self.nom or "Paramètres de l'association"

    def save(self, *args, **kwargs):
        """Force une instance unique (singleton, pk=1)."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> ParametresAssociation:
        """Retourne l'unique instance, en la créant au besoin."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Signataire(models.Model):
    """Personne habilitée à signer des documents (facture, devis, reçu).

    Peut être un membre du bureau (représentation de droit) ou un·e délégataire
    (délégation de signature actée par le bureau/CA — d'où `mention_delegation`).
    La signature est optionnelle sur les documents : un signataire n'est apposé
    que si on le choisit. L'image de signature est stockée en privé et embarquée
    dans le PDF au rendu (jamais exposée par une URL publique)."""

    nom = models.CharField(max_length=200)
    qualite = models.CharField(
        "qualité", max_length=120, help_text="Ex. président·e, trésorier·e, délégué·e."
    )
    mention_delegation = models.CharField(
        "mention de délégation",
        max_length=255,
        blank=True,
        help_text="Ex. « en vertu de la délégation du bureau du 12/03/2026 ».",
    )
    signature_image = models.ImageField(
        "image de signature",
        upload_to="signatures/",
        storage=StockagePrive,
        blank=True,
        help_text="Signature scannée (PNG/JPG). Optionnelle : à défaut, seuls le nom et la qualité s'affichent.",
    )
    membre = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signatures",
        verbose_name="membre associé",
    )
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "signataire"
        verbose_name_plural = "signataires"
        ordering = ["nom"]

    def __str__(self) -> str:
        return f"{self.nom} ({self.qualite})"

    def image_base64(self) -> str:
        """Renvoie l'image de signature en data URI base64 (ou "" si absente).

        Permet d'embarquer la signature directement dans le HTML rendu en PDF,
        sans exposer le fichier privé ni dépendre d'un accès disque au rendu."""
        if not self.signature_image:
            return ""
        with self.signature_image.open("rb") as fichier:
            donnees = base64.b64encode(fichier.read()).decode("ascii")
        mime = mimetypes.guess_type(self.signature_image.name)[0] or "image/png"
        return f"data:{mime};base64,{donnees}"


class Lieu(models.Model):
    """Lieu physique réutilisable (salle, théâtre) référencé par l'agenda."""

    nom = models.CharField(max_length=200)
    adresse = models.CharField(max_length=255, blank=True)
    code_postal = models.CharField("code postal", max_length=16, blank=True)
    ville = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "lieu"
        verbose_name_plural = "lieux"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom
