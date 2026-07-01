"""Modèles du front public (« vitrine »)."""

from __future__ import annotations

from django.db import models

from apps.common.models import Horodatage


class MessageContact(Horodatage):
    """Message reçu via le formulaire de contact public.

    Persisté en base (lu dans l'admin) plutôt qu'envoyé par e-mail tant que
    l'envoi n'est pas activé. Le consentement RGPD est horodaté à l'envoi.
    """

    nom = models.CharField(max_length=200)
    email = models.EmailField()
    sujet = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    consentement = models.BooleanField("consentement RGPD", default=False)
    date_consentement = models.DateTimeField("consentement le", null=True, blank=True)
    traite = models.BooleanField("traité", default=False)

    class Meta:
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"
        ordering = ["-date_creation"]

    def __str__(self) -> str:
        return f"{self.nom} — {self.sujet or '(sans sujet)'}"
