"""Un seul mécanisme de signature : le modèle `Signataire`.

Les deux champs texte (`signataire_nom`, `signataire_qualite`) ne servaient que
de repli sur le Cerfa, sans image ni mention de délégation. On les convertit en
un vrai `Signataire`, promu signataire par défaut, avant de les retirer — l'ordre
des opérations compte : les colonnes doivent encore exister au moment de lire
ce qu'elles contiennent.
"""

from django.db import migrations, models
import django.db.models.deletion


def convertir_signataire_texte(apps, schema_editor):
    """Reprend le signataire écrit en toutes lettres, s'il y en avait un.

    On ne crée rien si un signataire du même nom existe déjà : la conversion ne
    doit pas fabriquer un doublon de quelqu'un déjà saisi proprement."""
    Parametres = apps.get_model("coeur", "ParametresAssociation")
    Signataire = apps.get_model("coeur", "Signataire")
    params = Parametres.objects.first()
    if params is None or not params.signataire_nom:
        return
    signataire = Signataire.objects.filter(nom=params.signataire_nom).first()
    if signataire is None:
        signataire = Signataire.objects.create(
            nom=params.signataire_nom,
            qualite=params.signataire_qualite or "",
            actif=True,
        )
    params.signataire_par_defaut = signataire
    params.save(update_fields=["signataire_par_defaut"])


class Migration(migrations.Migration):
    dependencies = [
        ("coeur", "0013_membre_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametresassociation",
            name="signataire_par_defaut",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Proposé d'office sur chaque nouveau document ; "
                    "modifiable pièce par pièce."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="coeur.signataire",
                verbose_name="signataire par défaut",
            ),
        ),
        migrations.RunPython(convertir_signataire_texte, migrations.RunPython.noop),
        migrations.RemoveField(model_name="parametresassociation", name="signataire_nom"),
        migrations.RemoveField(model_name="parametresassociation", name="signataire_qualite"),
    ]
