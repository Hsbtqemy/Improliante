"""Services du domaine « Documents / GED ».

Le versionnement conserve l'historique : une nouvelle version devient la version
courante, l'ancienne est gardée (`courant=False`) et reliée par `remplace`.
"""

from __future__ import annotations

from django.db import transaction

from .models import Document


@transaction.atomic
def remplacer_document(ancien: Document, *, fichier, par=None) -> Document:
    """Crée une nouvelle version d'un document.

    Le nouveau document reprend les métadonnées de l'ancien (titre, dossier,
    confidentialité…), incrémente la version et devient courant ; l'ancien est
    conservé mais n'est plus courant (historique consultable)."""
    nouveau = Document.objects.create(
        titre=ancien.titre,
        dossier=ancien.dossier,
        fichier=fichier,
        description=ancien.description,
        confidentialite=ancien.confidentialite,
        version=ancien.version + 1,
        remplace=ancien,
        courant=True,
        date_validite=ancien.date_validite,
        cree_par=par,
    )
    ancien.courant = False
    ancien.save(update_fields=["courant"])
    return nouveau
