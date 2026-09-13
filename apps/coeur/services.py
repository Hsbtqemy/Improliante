"""Services métier du domaine « Cœur associatif ».

Création de compte membre par le bureau : on crée l'`Utilisateur` (identifiant =
e-mail, mot de passe INUTILISABLE) et le `Membre` rattaché, en une transaction.
Le nouveau membre définit lui-même son mot de passe via un **lien d'activation**
(token signé, à durée de vie limitée) — le bureau ne manipule jamais de mot de
passe en clair. Tant que le SMTP n'est pas activé, le lien est affiché à l'écran
et transmis hors-outil ; il pourra être envoyé par e-mail sans autre changement.

Page artiste (VIT-4) : `Membre` porte la version **publiée** — celle que le site
sert —, `BrouillonPageArtiste` le travail en cours. `publier_page_artiste`
recopie le second sur le premier, d'un seul coup et sous verrou.
"""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify

from .models import (
    CHAMPS_PUBLICS_ARTISTE,
    BrouillonPageArtiste,
    Membre,
    Utilisateur,
)

# Taille de la vedette (accordéon) sur la page association. L'accordéon ne scale
# pas au-delà de ~6-8 panneaux : on borne volontairement.
NB_VEDETTE = 6

# Le slug tient dans le champ (160) avec de la place pour un suffixe d'homonyme.
LONGUEUR_MAX_SLUG = 150


def slug_membre_unique(membre: Membre) -> str:
    """Slug libre pour l'adresse publique d'un membre : `/@prenom-nom`.

    Deux Jeanne Dupont donnent `jeanne-dupont` puis `jeanne-dupont-2` : le
    second arrivé est suffixé, jamais le premier — son adresse est peut-être
    déjà partagée. Un membre sans prénom ni nom (fiche créée à la volée) part
    de « membre » plutôt que d'une chaîne vide.

    L'unicité est aussi garantie en base par le champ ; deux créations vraiment
    simultanées lèveraient une `IntegrityError` plutôt que de se marcher dessus.
    """
    base = (slugify(membre.nom_complet) or "membre")[:LONGUEUR_MAX_SLUG]
    autres = Membre.objects.exclude(pk=membre.pk) if membre.pk else Membre.objects.all()
    candidat = base
    rang = 1
    while autres.filter(slug=candidat).exists():
        rang += 1
        candidat = f"{base}-{rang}"
    return candidat


def membres_en_vedette(nombre: int = NB_VEDETTE) -> list[Membre]:
    """Membres à afficher en vedette (accordéon) sur la page association.

    Les membres « à la une » visibles d'abord, complétés au hasard par d'autres
    membres visibles jusqu'à `nombre`, pour garder la vedette pleine et
    changeante même si peu de membres sont explicitement mis en avant. Bornée à
    `nombre` (l'accordéon ne scale pas au-delà de ~6-8)."""
    # La vedette affiche les liens de réseaux de chaque membre : sans le
    # préchargement, l'accordéon en demandait un par personne.
    visibles = (
        Membre.objects.filter(visible_sur_site=True)
        .select_related("user", "photo")
        .prefetch_related("liens_reseaux")
    )
    vedette = list(visibles.filter(mis_en_avant=True).order_by("?")[:nombre])
    manque = nombre - len(vedette)
    if manque > 0:
        deja = [m.pk for m in vedette]
        vedette += list(
            visibles.filter(mis_en_avant=False).exclude(pk__in=deja).order_by("?")[:manque]
        )
    return vedette


class OuvertureCompteImpossible(Exception):
    """Ouverture d'un accès en ligne impossible : le membre a déjà un compte,
    n'a pas d'e-mail, ou l'e-mail est déjà pris comme identifiant de connexion."""


@transaction.atomic
def creer_membre(
    *,
    prenom: str,
    nom: str,
    email: str = "",
    role_public: str = "",
    telephone: str = "",
) -> Membre:
    """Crée une fiche `Membre` (personne) SANS compte de connexion.

    L'identité (prénom, nom, e-mail) vit sur la fiche. Le compte — l'accès en
    ligne — est facultatif et s'ajoute ensuite via `ouvrir_compte`."""
    return Membre.objects.create(
        prenom=prenom,
        nom=nom,
        email=email,
        role_public=role_public,
        telephone=telephone,
    )


@transaction.atomic
def ouvrir_compte(membre: Membre) -> tuple[str, str]:
    """Ouvre un accès en ligne pour un membre existant.

    Crée l'`Utilisateur` (identifiant = e-mail, mot de passe INUTILISABLE),
    recopie l'identité de la fiche vers le compte, le rattache au membre, et
    renvoie `(uidb64, token)` pour le lien d'activation (le membre définit son
    mot de passe lui-même). Lève `OuvertureCompteImpossible` si le membre a déjà
    un compte, n'a pas d'e-mail, ou si l'e-mail est déjà pris comme identifiant."""
    if membre.a_un_compte:
        raise OuvertureCompteImpossible("Ce membre a déjà un compte de connexion.")
    email = (membre.email or "").strip()
    if not email:
        raise OuvertureCompteImpossible(
            "Un e-mail est nécessaire pour ouvrir un accès (il sert d'identifiant)."
        )
    if Utilisateur.objects.filter(username=email).exists():
        raise OuvertureCompteImpossible(
            "Cet e-mail est déjà utilisé comme identifiant de connexion."
        )
    user = Utilisateur(
        username=email,
        email=email,
        first_name=membre.prenom,
        last_name=membre.nom,
    )
    user.set_unusable_password()
    user.save()
    membre.user = user
    membre.save(update_fields=["user", "date_modification"])
    return jeton_activation(user)


def synchroniser_compte(membre: Membre) -> None:
    """Recopie l'identité de la fiche vers le compte lié, s'il existe.

    L'identifiant de connexion (`username`) n'est **pas** modifié : il reste
    stable même si l'e-mail de la fiche change (on ne casse pas la connexion)."""
    if not membre.a_un_compte:
        return
    user = membre.user
    user.first_name = membre.prenom
    user.last_name = membre.nom
    user.email = membre.email
    user.save(update_fields=["first_name", "last_name", "email"])


@transaction.atomic
def creer_compte_membre(
    *,
    first_name: str,
    last_name: str,
    email: str,
    role_public: str = "",
    telephone: str = "",
) -> Membre:
    """Raccourci : crée la fiche ET ouvre l'accès en ligne dans la foulée.

    Conservé pour les appels historiques ; équivaut à `creer_membre` suivi de
    `ouvrir_compte`. Le lien d'activation se récupère via `jeton_activation`.
    L'unicité de l'e-mail doit être vérifiée en amont (formulaire)."""
    membre = creer_membre(
        prenom=first_name,
        nom=last_name,
        email=email,
        role_public=role_public,
        telephone=telephone,
    )
    ouvrir_compte(membre)
    return membre


def jeton_activation(user: Utilisateur) -> tuple[str, str]:
    """Renvoie (uidb64, token) pour construire le lien d'activation d'un compte.

    Réutilise le générateur de token de Django (celui du « mot de passe
    oublié ») : le token devient caduc dès que le mot de passe est défini
    (usage unique) et expire selon `PASSWORD_RESET_TIMEOUT`."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    return uidb64, default_token_generator.make_token(user)


def definir_photo(cible, fichier, alt: str, *, cree_par=None):
    """Crée un `Media` image et le pose comme portrait de `cible`.

    `cible` porte le jeu de champs `ContenuPublicArtiste` : c'est soit un
    `Membre` — la page publiée, que seul le bureau écrit en direct —, soit un
    `BrouillonPageArtiste`. Une seule fonction pour les deux, sinon la version
    publiée et le brouillon finiraient par ne plus créer le même `Media`.
    """
    from apps.medias.models import Media

    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    cible.photo = media
    cible.save(update_fields=["photo", "date_modification"])
    return media


def retirer_photo(cible) -> None:
    """Détache le portrait de `cible` (le `Media` reste dans le socle)."""
    if cible.photo_id is None:
        return
    cible.photo = None
    cible.save(update_fields=["photo", "date_modification"])


def brouillon_de(membre: Membre) -> BrouillonPageArtiste:
    """Le brouillon de page de ce membre, créé au besoin.

    Un premier brouillon **vide** effacerait la page en le publiant : il part
    donc de ce que le public voit déjà, et l'artiste retouche. `get_or_create`
    plutôt qu'un `filter` suivi d'un `create` : deux onglets ouverts en même
    temps sur l'écran d'édition passent tous les deux par ici.
    """
    brouillon, _ = BrouillonPageArtiste.objects.get_or_create(
        membre=membre, defaults=dict(membre.contenu_public)
    )
    return brouillon


def brouillon_en_attente(membre: Membre) -> bool:
    """Vrai si le brouillon dit autre chose que la page publiée.

    Sans brouillon, il n'y a rien en attente : ne pas confondre « pas encore
    ouvert l'écran » et « des modifications non publiées ».
    """
    brouillon = BrouillonPageArtiste.objects.filter(membre=membre).first()
    if brouillon is None:
        return False
    return brouillon.contenu_public != membre.contenu_public


@transaction.atomic
def publier_page_artiste(membre: Membre, *, par=None) -> bool:
    """Recopie le brouillon sur la fiche publique, d'un seul coup.

    Une publication change **tous** les champs éditoriaux ou aucun : la copie et
    l'horodatage tiennent dans une transaction, et la fiche est relue sous
    verrou avant de décider — jamais l'instance qu'on a en main, qui peut avoir
    vieilli depuis l'affichage de l'écran.

    Recopie, et ne fusionne pas : une biographie effacée au brouillon s'efface
    en ligne. Un service qui ignorerait les valeurs vides rendrait un effacement
    impossible à publier, sans jamais le dire.

    Retourne `False` quand il n'y avait rien à publier — pas de brouillon, ou un
    brouillon qui ne dit rien de neuf. Publier deux fois (double-clic, retour
    arrière du navigateur) n'est pas une erreur : c'est un non-événement, et
    l'écran le dit plutôt que de lever.
    """
    courant = Membre.objects.select_for_update().get(pk=membre.pk)
    brouillon = BrouillonPageArtiste.objects.filter(membre=courant).first()
    if brouillon is None or brouillon.contenu_public == courant.contenu_public:
        return False

    for nom, valeur in brouillon.contenu_public.items():
        setattr(courant, nom, valeur)
    courant.save(update_fields=[*CHAMPS_PUBLICS_ARTISTE, "date_modification"])

    brouillon.publie_le = timezone.now()
    brouillon.publie_par = par
    brouillon.save(update_fields=["publie_le", "publie_par", "date_modification"])

    membre.refresh_from_db()
    return True


def utilisateur_depuis_uidb64(uidb64: str) -> Utilisateur | None:
    """Décode un uidb64 en `Utilisateur`, ou None si invalide/introuvable."""
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        return Utilisateur.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, Utilisateur.DoesNotExist):
        return None
