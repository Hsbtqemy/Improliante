"""Modèles du domaine « Documents / GED » (cf. cahier §9).

Arborescence de dossiers infinie (django-treebeard, materialized path) +
documents versionnés. Sert aussi à la vie associative (statuts, PV d'AG,
déclarations préfecture, récépissés).

Sécurité : les fichiers privés doivent être servis par une vue authentifiée
contrôlant les droits (ou X-Accel-Redirect), jamais par URL publique devinable,
et stockés hors racine web publique (cf. §9 et §10). La `FileField` ci-dessous
ne fait qu'organiser le stockage ; le contrôle d'accès se fait à la vue.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from treebeard.mp_tree import MP_Node

from apps.common.models import Horodatage
from apps.common.stockage import StockagePrive


class Dossier(MP_Node):
    """Dossier de la GED — nœud d'une arborescence infinie (treebeard)."""

    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    node_order_by = ["nom"]

    class Meta:
        verbose_name = "dossier"
        verbose_name_plural = "dossiers"

    def __str__(self) -> str:
        return self.nom


class Document(Horodatage):
    """Document rattaché à un dossier, versionné et à confidentialité réglable."""

    class Confidentialite(models.TextChoices):
        PRIVE = "prive", "Privé"
        MEMBRES = "membres", "Membres"
        PUBLIC = "public", "Public"

    titre = models.CharField(max_length=200)
    dossier = models.ForeignKey(
        Dossier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    # Stockage privé : hors racine web publique. L'accès passe obligatoirement
    # par une vue authentifiée (cf. apps.espace_membre.views.telecharger_document).
    fichier = models.FileField("fichier", upload_to="documents/%Y/%m/", storage=StockagePrive)
    description = models.TextField(blank=True)
    confidentialite = models.CharField(
        "confidentialité",
        max_length=8,
        choices=Confidentialite.choices,
        default=Confidentialite.PRIVE,
    )

    # Versionnement : une nouvelle version pointe vers celle qu'elle remplace ;
    # les anciennes versions sont conservées (`courant=False`).
    version = models.PositiveIntegerField(default=1)
    remplace = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions_suivantes",
        verbose_name="remplace la version",
    )
    courant = models.BooleanField("version courante", default=True)
    date_validite = models.DateField("date de validité", null=True, blank=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_ajoutes",
        verbose_name="ajouté par",
    )

    class Meta:
        verbose_name = "document"
        verbose_name_plural = "documents"
        ordering = ["titre", "-version"]

    def __str__(self) -> str:
        return f"{self.titre} (v{self.version})"
