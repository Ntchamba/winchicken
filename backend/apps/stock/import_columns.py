"""Which headers the stock Excel import accepts, and what it falls back to.

Same contract as apps/protocols/import_columns.py: synonyms are compared *normalised* (accents,
case, punctuation and spacing already folded by apps.core.column_matching.normalize), and edit
distance covers typos, so only genuine word differences belong here.

Defaults restate what the importer already does with an absent column — they never introduce a
new behaviour.
"""
from apps.core.column_matching import Column

COLUMNS = (
    Column(
        key='name', label='Article', required=True,
        synonyms=(
            'articles', 'nom', 'nom de l article', 'designation', 'libelle', 'produit',
            'produits', 'intitule', 'ressource', 'ressources', 'item', 'reference',
            'nom article', 'denomination', 'marchandise',
        ),
    ),
    Column(
        key='category', label='Catégorie', required=True,
        synonyms=(
            'categorie', 'cat', 'categ', 'type', 'type d article', 'rubrique', 'famille',
            'groupe', 'classe', 'nature', 'categories', 'segment',
        ),
    ),
    Column(
        key='detail', label='Détail',
        synonyms=(
            'details', 'precision', 'precisions', 'complement', 'sous type', 'stade',
            'stade alimentaire', 'phase', 'chaine du froid', 'commentaire', 'remarque',
            'note', 'description',
        ),
        default='',
        default_note='Sans colonne de détail, le sous-type de l\'article reste vide '
                     '(stade alimentaire « sans objet », pas de chaîne du froid).',
    ),
    Column(
        key='unit', label='Unité',
        synonyms=(
            'unite', 'unites', 'u', 'mesure', 'unite de mesure', 'um', 'conditionnement',
            'format',
        ),
        default='',
        default_note="Sans colonne d'unité, l'unité d'un article existant n'est pas modifiée.",
    ),
    Column(
        key='alert_threshold', label="Seuil d'alerte",
        synonyms=(
            'seuil', 'seuil alerte', 'seuil d alerte', 'seuil minimum', 'seuil mini',
            'stock minimum', 'stock mini', 'minimum', 'mini', 'alerte', 'seuil de reappro',
            'seuil de reapprovisionnement', 'quantite minimale',
        ),
        default=0,
        default_note="Sans colonne de seuil, le seuil d'alerte vaut 0 "
                     '(valeur déjà appliquée quand la case est vide).',
    ),
    Column(
        key='unit_price', label='Prix unitaire',
        synonyms=(
            'prix', 'prix u', 'pu', 'prix par unite', 'cout', 'cout unitaire', 'tarif',
            'valeur', 'prix achat', 'prix d achat', 'montant unitaire',
        ),
        default=0,
        default_note='Sans colonne de prix, le prix unitaire vaut 0 '
                     '(valeur déjà appliquée quand la case est vide).',
    ),
    Column(
        key='supplier', label='Fournisseur',
        synonyms=(
            'fournisseurs', 'vendeur', 'vendeurs', 'prestataire', 'distributeur', 'marchand',
            'societe', 'partenaire', 'nom du fournisseur',
        ),
        default=None,
        default_note="Sans colonne de fournisseur, aucun fournisseur n'est rattaché "
                     "(le fournisseur déjà enregistré sur un article existant est conservé).",
    ),
)
