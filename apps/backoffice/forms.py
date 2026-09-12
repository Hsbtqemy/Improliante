"""Formulaires du back-office."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.agenda.models import Evenement, Intervention
from apps.budget.models import (
    Adhesion,
    Categorie,
    RecuFiscal,
    Saison,
    SoldeTresorerie,
    Transaction,
)
from apps.coeur.models import (
    ContactPublic,
    Membre,
    ParametresAssociation,
    Signataire,
    Utilisateur,
)
from apps.common.fiches import ImagesFicheFormMixin
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.gouvernance.models import (
    BlocCompteRendu,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
    Sujet,
)
from apps.gouvernance.services import contenu_scelle
from apps.spectacles.models import LigneDistribution, Spectacle

# Format des <input type="datetime-local"> (sans fuseau ni secondes).
_FORMATS_DATETIME_LOCAL = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


def _restreindre_signataires_actifs(form):
    """Limite le champ `signataire` aux actifs et propose le défaut à la création.

    La présélection ne vaut que pour une pièce NEUVE : sur une pièce existante,
    elle réécrirait un choix déjà fait (ou en poserait un là où l'absence de
    signataire était volontaire)."""
    champ = form.fields["signataire"]
    champ.queryset = Signataire.objects.filter(actif=True)
    if form.instance.pk is None:
        # Lecture seule : `load()` créerait la ligne au passage, et rendre un
        # formulaire ne doit pas écrire en base.
        params = ParametresAssociation.objects.first()
        defaut = params.signataire_par_defaut if params else None
        if defaut is not None and defaut.actif:
            champ.initial = defaut
    champ.required = False


class RecuFiscalForm(forms.ModelForm):
    """Saisie / complément d'un reçu fiscal avant émission.

    Sert aussi bien à la saisie manuelle qu'au complément d'un reçu pré-rempli
    depuis une adhésion (le bureau ajoute notamment l'adresse du donateur,
    absente du modèle Membre mais obligatoire sur le Cerfa). Le formulaire ne
    fait que valider les données ; le numéro et le snapshot sont posés par le
    service `emettre_recu`.
    """

    class Meta:
        model = RecuFiscal
        fields = [
            "type_versement",
            "forme",
            "montant",
            "date_versement",
            "donateur_nom",
            "donateur_adresse",
            "donateur_code_postal",
            "donateur_ville",
            "signataire",
        ]
        widgets = {
            "date_versement": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_versement"].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)

    def clean_montant(self) -> Decimal:
        montant = self.cleaned_data["montant"]
        if montant is None or montant <= 0:
            raise forms.ValidationError("Le montant doit être strictement positif.")
        return montant


class ClientForm(forms.ModelForm):
    """Création / édition d'un client (destinataire de facture)."""

    class Meta:
        model = Client
        fields = [
            "nom",
            "adresse",
            "code_postal",
            "ville",
            "email",
            "telephone",
            "siret",
            "numero_tva",
        ]
        widgets = {"adresse": forms.Textarea(attrs={"rows": 2})}


class FactureForm(forms.ModelForm):
    """En-tête d'une facture. Numéro, date d'émission et statut sont posés par
    le service `valider_facture`, jamais saisis à la main."""

    class Meta:
        model = Facture
        fields = ["client", "objet", "date_echeance", "mentions_legales", "signataire"]
        widgets = {
            "date_echeance": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "mentions_legales": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_echeance"].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)


# Lignes d'une facture éditées en bloc avec l'en-tête (formset inline).
LigneFactureFormSet = forms.inlineformset_factory(
    Facture,
    LigneFacture,
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva"],
    extra=1,  # une seule ligne vide ; « + Ajouter une ligne » (JS) pour d'autres
    can_delete=True,
)


class DevisForm(forms.ModelForm):
    """En-tête d'un devis. Le numéro est attribué par le service (non saisi)."""

    class Meta:
        model = Devis
        fields = ["client", "objet", "date", "date_validite", "conditions", "signataire"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_validite": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "conditions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date", "date_validite"):
            self.fields[champ].input_formats = ["%Y-%m-%d"]
        _restreindre_signataires_actifs(self)


LigneDevisFormSet = forms.inlineformset_factory(
    Devis,
    LigneDevis,
    fields=["designation", "quantite", "prix_unitaire_ht", "taux_tva"],
    extra=1,  # une seule ligne vide ; « + Ajouter une ligne » (JS) pour d'autres
    can_delete=True,
)


# --- Budget -----------------------------------------------------------------


class TransactionForm(forms.ModelForm):
    """Recette ou dépense, prévue ou réalisée, rattachée à une saison."""

    class Meta:
        model = Transaction
        fields = ["saison", "type_flux", "statut", "libelle", "montant", "date", "categorie"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]

    def clean_montant(self) -> Decimal:
        montant = self.cleaned_data["montant"]
        if montant is None or montant <= 0:
            raise forms.ValidationError("Le montant doit être strictement positif.")
        return montant


class SaisonForm(forms.ModelForm):
    class Meta:
        model = Saison
        fields = ["nom", "date_debut", "date_fin"]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date_debut", "date_fin"):
            self.fields[champ].input_formats = ["%Y-%m-%d"]


class SoldeTresorerieForm(forms.ModelForm):
    """Saisie du solde en banque de référence (dernier pointage)."""

    class Meta:
        model = SoldeTresorerie
        fields = ["montant", "date_pointage", "note"]
        widgets = {
            "date_pointage": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "note": forms.TextInput(attrs={"placeholder": "ex. d'après le relevé du mois"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_pointage"].input_formats = ["%Y-%m-%d"]


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ["nom", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


# --- Paramètres de l'association --------------------------------------------


# Les réglages sont un SEUL modèle (singleton) édité par TROIS écrans, parce
# qu'ils ne servent pas le même public : le greffe et le fisc d'un côté, les
# visiteurs du site de l'autre, la page Contact enfin. Chaque formulaire ne
# déclare que ses colonnes — les vues n'écrivent que celles-là (`update_fields`),
# pour qu'un écran ne recopie jamais par-dessus ce qu'un autre vient de changer.


class IdentiteAssociationForm(forms.ModelForm):
    """Identité légale : ce qui s'imprime en tête des documents officiels."""

    class Meta:
        model = ParametresAssociation
        fields = [
            "nom",
            "objet",
            "adresse",
            "code_postal",
            "ville",
            "numero_rna",
            "numero_siret",
            "article_cgi",
            "iban",
            "bic",
            "mention_tva",
        ]
        widgets = {"objet": forms.Textarea(attrs={"rows": 2})}


class TextesSiteForm(forms.ModelForm):
    """Les deux textes qui portent la page d'accueil et la page « L'association »."""

    class Meta:
        model = ParametresAssociation
        fields = ["accroche", "presentation"]
        widgets = {"presentation": forms.Textarea(attrs={"rows": 3})}


class SignataireForm(forms.ModelForm):
    """Création / édition d'un signataire depuis le bureau.

    L'image de signature part en stockage privé (règle 5) : elle n'est jamais
    servie par une URL devinable, seulement embarquée dans le PDF au rendu."""

    class Meta:
        model = Signataire
        fields = ["nom", "qualite", "mention_delegation", "signature_image", "membre", "actif"]


class SignataireParDefautForm(forms.ModelForm):
    """Choix du signataire proposé d'office sur les nouveaux documents."""

    class Meta:
        model = ParametresAssociation
        fields = ["signataire_par_defaut"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Un signataire retiré du service ne peut pas devenir le défaut : il
        # serait proposé sur chaque pièce tout en étant absent des choix.
        self.fields["signataire_par_defaut"].queryset = Signataire.objects.filter(actif=True)


class ContactPubliqueForm(forms.ModelForm):
    """Coordonnées publiées sur la page Contact, à côté du formulaire."""

    class Meta:
        model = ParametresAssociation
        fields = ["email_public", "telephone_public", "afficher_adresse_postale"]


# Interlocuteurs publics, édités sur l'écran « Page Contact » : les paramètres
# étant un singleton, l'inline formset y a exactement un parent.
ContactPublicFormSet = forms.inlineformset_factory(
    ParametresAssociation,
    ContactPublic,
    fields=["role", "nom", "email", "telephone", "ordre"],
    extra=1,
    can_delete=True,
)


# --- Gouvernance ------------------------------------------------------------


class ReunionForm(forms.ModelForm):
    """En-tête d'une réunion, transitions de statut comprises.

    Sur une réunion ARCHIVÉE, seul le statut reste saisissable : le titre, la
    date et le lieu font partie du dossier de la séance. Le statut, lui, doit
    pouvoir reculer — c'est le seul chemin pour rouvrir une réunion close par
    erreur, et une clôture sans retour serait une impasse."""

    class Meta:
        model = Reunion
        fields = ["titre", "type_reunion", "statut", "date", "lieu_texte", "convocation_texte"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "convocation_texte": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        if self.instance.pk and contenu_scelle(self.instance):
            # `disabled` ignore la valeur envoyée et garde celle de la base :
            # un envoi forgé ne réécrit pas l'en-tête d'une séance close.
            for nom, champ in self.fields.items():
                champ.disabled = nom != "statut"


class SujetOrdreDuJourForm(forms.ModelForm):
    """Ajout d'un sujet à l'ordre du jour d'une réunion (réunion posée par la vue)."""

    class Meta:
        model = Sujet
        fields = ["titre", "description", "priorite", "ordre_du_jour"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


def _membres_actifs():
    return Membre.objects.filter(actif=True)


class PresenceForm(forms.ModelForm):
    class Meta:
        model = Presence
        fields = ["membre", "statut", "peut_voter"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membre"].queryset = _membres_actifs()


class PouvoirForm(forms.ModelForm):
    class Meta:
        model = Pouvoir
        fields = ["mandant", "mandataire"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mandant"].queryset = _membres_actifs()
        self.fields["mandataire"].queryset = _membres_actifs()

    def clean(self):
        donnees = super().clean()
        if donnees.get("mandant") and donnees.get("mandant") == donnees.get("mandataire"):
            raise forms.ValidationError("Le mandant et le mandataire doivent être différents.")
        return donnees


class ResolutionForm(forms.ModelForm):
    class Meta:
        model = Resolution
        fields = [
            "intitule",
            "texte",
            "type_majorite",
            "sujet",
            "nombre_pour",
            "nombre_contre",
            "nombre_abstention",
            "ordre",
        ]
        widgets = {"texte": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, reunion=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ne proposer que les sujets de cette réunion comme rattachement.
        if reunion is not None:
            self.fields["sujet"].queryset = reunion.sujets.all()
        self.fields["sujet"].required = False


class BlocCompteRenduForm(forms.ModelForm):
    """Ajout d'un bloc de récit au déroulé (la réunion est posée par le service).

    `apres_sujet` n'offre que les points de CETTE réunion : la position d'un
    bloc ne se choisit pas dans l'ordre du jour d'une autre séance. Cet écran
    lisait `request.POST` en direct — d'où un bloc sans texte, qu'aucune
    validation n'arrêtait."""

    class Meta:
        model = BlocCompteRendu
        fields = ["apres_sujet", "titre", "texte"]
        widgets = {"texte": forms.Textarea(attrs={"rows": 3})}
        labels = {"apres_sujet": "Position", "titre": "Intertitre (optionnel)"}

    def __init__(self, *args, reunion=None, **kwargs):
        super().__init__(*args, **kwargs)
        champ = self.fields["apres_sujet"]
        champ.required = False
        champ.empty_label = "En préambule (avant le 1er point)"
        if reunion is not None:
            champ.queryset = reunion.sujets.order_by("ordre_du_jour", "id")


class CompteRenduForm(forms.Form):
    """Le compte rendu d'une séance : synthèse, notes par point, blocs de récit.

    Un champ par point de l'ordre du jour, trois par bloc de récit, construits
    depuis LA réunion — un envoi ne peut donc pas écrire les notes d'une autre
    séance. Cet écran lisait `request.POST` en direct : ni validation, ni
    longueur maximale, et surtout aucun endroit naturel pour poser la règle de
    clôture. C'est ainsi qu'une réunion archivée est restée éditable sans que
    personne ne le voie (inventaire ARCH-01, points 2 et 5)."""

    synthese = forms.CharField(
        label="Conclusion / synthèse",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Clôture, remarques finales…"}),
    )

    def __init__(self, *args, reunion, **kwargs):
        super().__init__(*args, **kwargs)
        self.reunion = reunion
        self._sujets = list(reunion.sujets.order_by("ordre_du_jour", "id"))
        self._blocs = list(reunion.blocs.all())
        self.fields["synthese"].initial = reunion.compte_rendu_texte
        for sujet in self._sujets:
            self.fields[f"notes_{sujet.pk}"] = forms.CharField(
                label="Notes / décision",
                required=False,
                initial=sujet.notes,
                widget=forms.Textarea(
                    attrs={"rows": 3, "placeholder": "Ce qui a été dit ou décidé…"}
                ),
            )
        for bloc in self._blocs:
            self.fields[f"bloc_{bloc.pk}_titre"] = forms.CharField(
                label="Intertitre du bloc de récit",
                required=False,
                max_length=BlocCompteRendu._meta.get_field("titre").max_length,
                initial=bloc.titre,
                widget=forms.TextInput(
                    attrs={
                        "placeholder": "Intertitre (optionnel)",
                        "class": "cr-bloc__titre",
                        # Pas d'étiquette visible dans un bloc de récit : deux
                        # libellés par bloc feraient du bruit à l'œil, et le
                        # champ doit rester annoncé à l'oreille.
                        "aria-label": "Intertitre du bloc de récit",
                    }
                ),
            )
            self.fields[f"bloc_{bloc.pk}_texte"] = forms.CharField(
                label="Texte du bloc de récit",
                required=False,
                initial=bloc.texte,
                widget=forms.Textarea(attrs={"rows": 3, "aria-label": "Texte du bloc de récit"}),
            )
            self.fields[f"supprimer_bloc_{bloc.pk}"] = forms.BooleanField(
                label="Supprimer ce bloc", required=False
            )

    def points(self):
        """Chaque point de l'ordre du jour avec son champ de notes (gabarit)."""
        for sujet in self._sujets:
            yield sujet, self[f"notes_{sujet.pk}"]

    def blocs(self):
        """Chaque bloc de récit avec ses champs : titre, texte, suppression."""
        for bloc in self._blocs:
            yield (
                bloc,
                self[f"bloc_{bloc.pk}_titre"],
                self[f"bloc_{bloc.pk}_texte"],
                self[f"supprimer_bloc_{bloc.pk}"],
            )

    def donnees_du_compte_rendu(self) -> dict:
        """Traduit les champs à plat en arguments d'`enregistrer_compte_rendu`.

        Un champ ABSENT de l'envoi est laissé tel quel en base, et non vidé : la
        page peut avoir été rendue avant qu'un point n'existe, et ce qu'elle n'a
        pas montré ne s'écrase pas. `cleaned_data` ne distingue pas les deux —
        un champ optionnel absent y vaut la chaîne vide."""
        propres = self.cleaned_data
        return {
            "synthese": propres.get("synthese", ""),
            "notes": {
                sujet.pk: propres[f"notes_{sujet.pk}"]
                for sujet in self._sujets
                if f"notes_{sujet.pk}" in self.data
            },
            "blocs": {
                bloc.pk: {
                    "titre": propres[f"bloc_{bloc.pk}_titre"],
                    "texte": propres[f"bloc_{bloc.pk}_texte"],
                }
                for bloc in self._blocs
                if f"bloc_{bloc.pk}_texte" in self.data
            },
            "blocs_supprimes": {
                bloc.pk for bloc in self._blocs if propres[f"supprimer_bloc_{bloc.pk}"]
            },
        }


class MembreForm(forms.ModelForm):
    """Fiche d'une personne (adhérent / membre), pour la création et l'édition.

    L'identité vit sur la fiche ; le compte de connexion est facultatif. À la
    création, cocher « ouvrir un accès » crée le compte et le lien d'activation
    (le membre y choisit son mot de passe). En édition, l'ouverture d'accès passe
    par un bouton dédié : la case est retirée."""

    ouvrir_acces = forms.BooleanField(
        label="Ouvrir un accès en ligne maintenant",
        required=False,
        help_text="Crée un compte de connexion et un lien d'activation. Nécessite un e-mail.",
    )

    class Meta:
        model = Membre
        fields = ["prenom", "nom", "email", "telephone", "role_public"]

    def __init__(self, *args, edition=False, **kwargs):
        super().__init__(*args, **kwargs)
        if edition:
            self.fields.pop("ouvrir_acces")

    def clean_email(self) -> str:
        # L'e-mail sert d'identifiant de connexion : on le canonise en minuscules.
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        donnees = super().clean()
        if donnees.get("ouvrir_acces"):
            email = donnees.get("email", "")
            if not email:
                self.add_error("email", "Un e-mail est nécessaire pour ouvrir un accès.")
            elif Utilisateur.objects.filter(username__iexact=email).exists():
                self.add_error("email", "Un compte existe déjà avec cet e-mail.")
        return donnees


class MembreRapideForm(forms.ModelForm):
    """Création express d'une personne (sans compte) depuis l'écran Adhésions."""

    class Meta:
        model = Membre
        fields = ["prenom", "nom", "email"]

    def clean_email(self) -> str:
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        donnees = super().clean()
        if not (donnees.get("prenom") or donnees.get("nom")):
            raise forms.ValidationError("Indiquez au moins un prénom ou un nom.")
        return donnees


class AdhesionForm(forms.ModelForm):
    """Adhésion d'une personne pour une saison (statut + montants attendu/versé)."""

    class Meta:
        model = Adhesion
        fields = ["membre", "saison", "statut", "montant_attendu", "montant_verse", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, membre_optionnel=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].input_formats = ["%Y-%m-%d"]
        if membre_optionnel:
            # Création à la volée possible : la personne peut être créée dans la
            # foulée, donc « membre » n'est pas obligatoire ici (arbitré en vue).
            self.fields["membre"].required = False

    def clean_montant_attendu(self) -> Decimal:
        return self._montant_positif_ou_nul("montant_attendu")

    def clean_montant_verse(self) -> Decimal:
        return self._montant_positif_ou_nul("montant_verse")

    def _montant_positif_ou_nul(self, champ) -> Decimal:
        montant = self.cleaned_data.get(champ)
        if montant is not None and montant < 0:
            raise forms.ValidationError("Le montant ne peut pas être négatif.")
        return montant


# --- Programmation : événements & projets (gestion directe par le bureau) ----


class EvenementBureauForm(ImagesFicheFormMixin, forms.ModelForm):
    """Création / édition d'un événement par le bureau.

    Superset du formulaire membre : expose en plus `visibilite`, le `lieu` (fiche)
    et un `spectacle` non restreint aux projets d'un membre. Le statut de
    modération est piloté par les boutons de la vue (« Publier » / « brouillon »)."""

    class Meta:
        model = Evenement
        fields = [
            "titre",
            "description",
            "date_debut",
            "date_fin",
            "lieu",
            "lieu_texte",
            "visibilite",
            "spectacle",
            # Ouvre (ou non) la feuille d'inscription publique : vide = pas
            # d'inscription. Sans ce champ, la jauge ne serait réglable que
            # depuis l'admin Django, et la fonction resterait lettre morte.
            "places_max",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "date_debut": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "date_fin": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("date_debut", "date_fin"):
            self.fields[champ].input_formats = _FORMATS_DATETIME_LOCAL
        self.fields["spectacle"].required = False
        self.fields["lieu"].required = False


class ProjetBureauForm(ImagesFicheFormMixin, forms.ModelForm):
    """Création / édition d'un projet/spectacle par le bureau.

    Superset du formulaire membre : `type_portage` complet (dont « association »)
    et `porteurs`. La mise en scène se saisit comme une ligne de distribution
    (rôle libre), pas comme un champ dédié. Statut de modération piloté par la vue."""

    class Meta:
        model = Spectacle
        fields = [
            "titre",
            "synopsis",
            "note_intention",
            "type_portage",
            "statut_projet",
            "genre",
            "public_vise",
            "duree_minutes",
            "porteurs",
        ]
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 4}),
            "note_intention": forms.Textarea(attrs={"rows": 4}),
            # Cases à cocher plutôt que le <select multiple> par défaut : ajout /
            # retrait évidents, accessible et confortable sur mobile.
            "porteurs": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["porteurs"].required = False


# Intervenants d'un événement (membre + rôle) et distribution d'un projet
# (membre OU nom externe + rôle) — édités via formsets inline, comme les lignes
# de facture. La validation modèle (unicité / « membre XOR nom_externe ») remonte.
InterventionFormSet = forms.inlineformset_factory(
    Evenement, Intervention, fields=["membre", "role"], extra=1, can_delete=True
)
LigneDistributionFormSet = forms.inlineformset_factory(
    Spectacle, LigneDistribution, fields=["membre", "nom_externe", "role"], extra=1, can_delete=True
)
