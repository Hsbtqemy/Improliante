"""Tests du domaine « Documents / GED » : versionnement."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.models import Document
from apps.documents.services import remplacer_document


def _document(**extra):
    donnees = {
        "titre": "Statuts",
        "confidentialite": Document.Confidentialite.MEMBRES,
        "fichier": SimpleUploadedFile("statuts.pdf", b"v1", content_type="application/pdf"),
    }
    donnees.update(extra)
    return Document.objects.create(**donnees)


def test_remplacer_document_cree_une_nouvelle_version_courante(db):
    ancien = _document()
    nouveau = remplacer_document(
        ancien,
        fichier=SimpleUploadedFile("statuts-v2.pdf", b"v2", content_type="application/pdf"),
    )
    ancien.refresh_from_db()
    assert nouveau.version == 2
    assert nouveau.courant is True
    assert nouveau.remplace == ancien
    assert nouveau.titre == ancien.titre
    assert nouveau.confidentialite == ancien.confidentialite
    # L'ancienne version est conservée mais n'est plus courante.
    assert ancien.courant is False


def test_versions_successives_incrementent(db):
    v1 = _document()
    v2 = remplacer_document(v1, fichier=SimpleUploadedFile("v2.pdf", b"v2"))
    v3 = remplacer_document(v2, fichier=SimpleUploadedFile("v3.pdf", b"v3"))
    assert [v1.version, v2.version, v3.version] == [1, 2, 3]
    assert Document.objects.filter(courant=True).count() == 1  # seule v3 est courante
