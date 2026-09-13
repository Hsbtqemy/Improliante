"""Tests du domaine « Médias » : préparation des images téléversées.

Le traitement (réduction + vignette) est un CONFORT posé sur le chemin de
l'enregistrement : il doit alléger ce qui est trop lourd, ne rien refaire à
chaque `save`, et ne jamais faire échouer un téléversement — pas même sur un
fichier qui n'est pas une image.
"""

from __future__ import annotations

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from apps.medias.models import Media
from apps.medias.services import LARGEUR_MAX, LARGEUR_VIGNETTE


def _octets(largeur, hauteur, format="JPEG", mode="RGB"):
    """Une vraie image, pour que Pillow ait quelque chose à ouvrir."""
    tampon = io.BytesIO()
    couleur = (200, 30, 60) if mode == "RGB" else (200, 30, 60, 128)
    Image.new(mode, (largeur, hauteur), couleur).save(tampon, format)
    return tampon.getvalue()


def _media(nom="lot17-photo.jpg", largeur=3000, hauteur=4000, format="JPEG", mode="RGB"):
    return Media.objects.create(
        fichier=SimpleUploadedFile(nom, _octets(largeur, hauteur, format, mode)),
        alt="Une photo",
    )


def test_une_image_trop_large_est_reduite(db):
    """Une photo de téléphone fait 4 000 px : elle habillait telle quelle une
    carte de 300. Le fichier servi est réécrit SOUS LE MÊME NOM — passer par
    `save()` en laisserait deux, et changerait l'URL."""
    octets_origine = _octets(3000, 4000)
    # Nom distinctif : le dossier de médias des tests est partagé par toute la
    # suite, et Django suffixe un nom déjà pris — l'assertion sur le nom dirait
    # alors le contraire de ce qu'elle vérifie.
    media = Media.objects.create(
        fichier=SimpleUploadedFile("lot17-reduite.jpg", octets_origine), alt="Une photo"
    )

    media.refresh_from_db()
    assert media.largeur == LARGEUR_MAX
    assert media.hauteur == 2667  # ratio conservé (4000 × 2000 / 3000)
    assert media.fichier.size < len(octets_origine)
    assert media.fichier.name.endswith("lot17-reduite.jpg")


def test_une_vignette_accompagne_l_image(db):
    """C'est elle que le `srcset` propose au téléphone."""
    media = _media()
    media.refresh_from_db()

    assert media.vignette
    assert media.vignette_largeur == LARGEUR_VIGNETTE
    assert media.vignette_hauteur == 800
    assert media.vignette.size < media.fichier.size


def test_une_petite_image_garde_sa_taille_et_n_a_pas_de_vignette(db):
    """En dessous de la largeur de vignette, une variante ne servirait à rien :
    le `srcset` n'aurait que deux fois le même fichier."""
    media = _media("lot17-petite.png", largeur=400, hauteur=300, format="PNG")
    media.refresh_from_db()

    assert (media.largeur, media.hauteur) == (400, 300)
    assert not media.vignette


def test_le_traitement_ne_se_rejoue_pas_a_chaque_enregistrement(db):
    """Sans ce garde, chaque `save` rouvrait le fichier et le réencodait — une
    perte de qualité à chaque passage, et une image relue pour rien."""
    media = _media()
    media.refresh_from_db()
    taille = media.fichier.size
    vignette = media.vignette.name

    media.legende = "Vue de la salle"
    media.save()

    media.refresh_from_db()
    assert media.fichier.size == taille
    assert media.vignette.name == vignette


def test_remplacer_le_fichier_refait_dimensions_et_vignette(db):
    """Sinon le média annonce les dimensions de l'image d'AVANT, et sert une
    vignette qui ne la montre plus."""
    media = _media()
    media.refresh_from_db()
    ancienne = media.vignette.name

    media.fichier = SimpleUploadedFile("lot17-autre.jpg", _octets(1800, 1200))
    media.save()

    media.refresh_from_db()
    assert (media.largeur, media.hauteur) == (1800, 1200)
    assert media.vignette.name != ancienne
    assert media.vignette_hauteur == 400  # 1200 × 600 / 1800


def test_un_png_transparent_reste_un_png(db):
    """Réencoder en JPEG « pour gagner des octets » aplatirait la transparence
    et obligerait à renommer le fichier, donc à changer son URL."""
    media = _media("lot17-logo.png", largeur=2400, hauteur=2400, format="PNG", mode="RGBA")
    media.refresh_from_db()

    assert media.fichier.name.endswith(".png")
    with media.fichier.open("rb") as fichier:
        image = Image.open(fichier)
        assert image.format == "PNG"
        assert image.mode in ("RGBA", "LA", "P")


def test_un_fichier_illisible_n_empeche_pas_l_enregistrement(db):
    """Le traitement est un confort : un fichier tronqué, ou un chemin qui ne
    pointe sur rien (fixtures, import), ne doit pas faire tomber le média."""
    casse = Media.objects.create(
        fichier=SimpleUploadedFile("lot17-faux.jpg", b"ceci n'est pas une image"), alt="x"
    )
    fantome = Media.objects.create(fichier="medias/2020/01/absente.jpg", alt="y")

    for media in (casse, fantome):
        media.refresh_from_db()
        assert media.largeur is None
        assert not media.vignette


def test_la_commande_traite_les_medias_deja_en_base(db):
    """Les médias téléversés avant ce traitement n'ont ni dimensions ni
    vignette : le passage ne se déclenche qu'à l'enregistrement."""
    media = _media()
    # On remet l'état d'avant, comme si le média datait du dépôt d'hier.
    Media.objects.filter(pk=media.pk).update(
        largeur=None, hauteur=None, vignette="", vignette_largeur=None, vignette_hauteur=None
    )

    call_command("preparer_medias")

    media.refresh_from_db()
    assert media.largeur == LARGEUR_MAX
    assert media.vignette


def test_une_image_de_brouillon_est_reduite_mais_sans_vignette(db):
    """Une image pas encore publiée est traitée comme les autres — l'aperçu ne
    doit pas télécharger l'original de 5 Mio — mais SANS vignette : celle-ci
    irait dans le stockage public, et une miniature d'une image qu'on protège
    est une fuite de cette image."""
    media = Media.objects.create(
        fichier_prive=SimpleUploadedFile("brouillon.jpg", _octets(3000, 4000)),
        alt="Portrait de brouillon",
    )

    assert media.est_prive is True
    assert media.largeur == LARGEUR_MAX
    assert not media.vignette


def test_la_commande_reprend_aussi_les_images_de_brouillon(db):
    """Elle écartait les médias sur le seul `fichier` : un média de brouillon
    porte bien une image, simplement pas dans la racine web. Le filtre aveugle
    les aurait laissés sans dimensions pour toujours — donc sans place réservée
    dans l'écran d'édition."""
    media = Media.objects.create(
        fichier_prive=SimpleUploadedFile("repris.jpg", _octets(1200, 900)),
        alt="Portrait de brouillon",
    )
    Media.objects.filter(pk=media.pk).update(largeur=None, hauteur=None)

    call_command("preparer_medias")

    media.refresh_from_db()
    assert media.largeur == 1200
    assert not media.vignette  # toujours pas : le média n'est pas publié
