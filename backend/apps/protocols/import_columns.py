"""Which headers the protocol Excel import accepts, and what it falls back to.

Kept separate from the parsing logic on purpose: adding a spelling a user turned up with should
never mean touching `xlsx_import.py`. Add the string to the right `synonyms` tuple and that's it.

Synonyms are compared *normalised* (see apps.core.column_matching.normalize): accents, case,
punctuation and extra spaces are already handled, so only genuine word differences belong here
— "conso" yes, "Consommation " or "consommation" no. Edit distance covers the rest, so simple
typos ("catgorie") don't need listing either.
"""
from apps.core.column_matching import Column

COLUMNS = (
    Column(
        key='category', label='Catégorie', required=True,
        synonyms=(
            'categorie', 'cat', 'categ', 'categorie de protocole', 'type', 'type de protocole',
            'rubrique', 'famille', 'groupe', 'poste', 'volet', 'section', 'domaine',
            'categories', 'nature',
        ),
    ),
    Column(
        key='from_value', label='De', required=True,
        synonyms=(
            'du', 'debut', 'jour de debut', 'jour debut', 'a partir de', 'a partir du',
            'depuis', 'jour de', 'age debut', 'age de debut', 'debut jour', 'j debut',
            'premier jour', 'de jour', 'jour min', 'min',
        ),
    ),
    Column(
        key='to_value', label='À',
        synonyms=(
            'a', 'au', 'fin', 'jusqu a', 'jusqua', 'jusqu au', 'jour de fin', 'jour fin',
            'age fin', 'age de fin', 'fin jour', 'j fin', 'dernier jour', 'a jour', 'jour max',
            'max',
        ),
        default=None,
        default_note="Sans colonne de fin, chaque ligne court jusqu'à la fin du cycle "
                     "(comportement déjà appliqué quand la case « À » est vide).",
    ),
    Column(
        key='what', label='Action', required=True,
        synonyms=(
            'actions', 'intitule', 'libelle', 'tache', 'taches', 'operation', 'intervention',
            'quoi', 'description', 'acte', 'soin', 'produit', 'designation', 'nom',
            'nom de l action', 'a faire',
        ),
    ),
    Column(
        key='details', label='Détails',
        synonyms=(
            'detail', 'commentaire', 'commentaires', 'remarque', 'remarques', 'note', 'notes',
            'precision', 'precisions', 'observation', 'observations', 'info', 'informations',
            'posologie', 'dosage',
        ),
        default='',
        default_note='Sans colonne de détails, les lignes sont importées sans commentaire.',
    ),
    Column(
        key='consumption', label='Consommation',
        synonyms=(
            'conso', 'ressource', 'ressources', 'article', 'articles', 'produit consomme',
            'intrant', 'intrants', 'stock', 'article de stock', 'matiere', 'aliment',
            'quantite consommee', 'qte consommee', 'consommation journaliere',
            'conso journaliere', 'nom de la ressource',
        ),
        default=None,
        default_note="Sans colonne de consommation, aucune ligne n'est reliée au stock "
                     '(la liaison reste modifiable ensuite, ligne par ligne).',
    ),
    Column(
        key='unit', label='Unité',
        synonyms=(
            'unite', 'unites', 'u', 'mesure', 'unite de mesure', 'unite de la ressource',
            'um', 'unite article',
        ),
        default='kg',
        default_note='Sans colonne d\'unité, une ressource créée par l\'import prend « kg » '
                     '— l\'unité déjà utilisée par une ressource existante n\'est jamais modifiée.',
    ),
    Column(
        key='quantity_per_day', label='Quantité/jour',
        synonyms=(
            'quantite jour', 'qte jour', 'qte j', 'quantite par jour', 'qte par jour',
            'quantite journaliere', 'qte journaliere', 'quantite', 'qte', 'quantite quotidienne',
            'ration', 'ration journaliere', 'dose jour', 'par jour', 'q j',
        ),
        default=None,
        default_note='Sans colonne de quantité, aucune consommation journalière '
                     "n'est pré-remplie.",
    ),
    Column(
        key='time_slots', label='Créneaux',
        synonyms=(
            'creneaux', 'creneau', 'horaire', 'horaires', 'plage horaire', 'plages horaires',
            'heure', 'heures', 'plage', 'plages', 'tranche horaire', 'tranches horaires',
            'moment', 'moments', 'heure de distribution', 'heures de distribution', 'timing',
        ),
        default=(),
        default_note='Sans colonne de créneaux, les lignes sont importées sans horaire précis.',
    ),
)
