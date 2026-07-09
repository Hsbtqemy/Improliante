"""Fait de `Membre` la fiche de la personne : identité propre (prénom/nom/e-mail)
et compte de connexion (`user`) rendu optionnel — un adhérent peut exister sans
accès en ligne. Recopie l'identité des comptes existants vers la fiche."""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_identite(apps, schema_editor):
    """Recopie prénom/nom/e-mail du compte vers la fiche pour les membres existants."""
    Membre = apps.get_model("coeur", "Membre")
    for membre in Membre.objects.select_related("user").filter(user__isnull=False):
        user = membre.user
        membre.prenom = user.first_name or ""
        membre.nom = user.last_name or ""
        membre.email = user.email or ""
        membre.save(update_fields=["prenom", "nom", "email"])


def noop(apps, schema_editor):
    """Sens inverse : rien à défaire (les champs sont simplement supprimés)."""


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("coeur", "0007_parametresassociation_bic_parametresassociation_iban_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="membre",
            name="prenom",
            field=models.CharField(blank=True, max_length=150, verbose_name="prénom"),
        ),
        migrations.AddField(
            model_name="membre",
            name="nom",
            field=models.CharField(blank=True, max_length=150, verbose_name="nom"),
        ),
        migrations.AddField(
            model_name="membre",
            name="email",
            field=models.EmailField(
                blank=True,
                help_text="Sert d'identifiant de connexion si un accès en ligne est ouvert.",
                max_length=254,
                verbose_name="e-mail",
            ),
        ),
        migrations.AlterField(
            model_name="membre",
            name="user",
            field=models.OneToOneField(
                blank=True,
                help_text="Compte de connexion, si la personne a un accès en ligne (facultatif).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="membre",
                to=settings.AUTH_USER_MODEL,
                verbose_name="compte utilisateur",
            ),
        ),
        migrations.AlterModelOptions(
            name="membre",
            options={
                "ordering": ["nom", "prenom"],
                "verbose_name": "membre",
                "verbose_name_plural": "membres",
            },
        ),
        migrations.RunPython(backfill_identite, noop),
    ]
