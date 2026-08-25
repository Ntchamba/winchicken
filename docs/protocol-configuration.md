# Configuration du protocole de bâtiment

Référence pour l'écran de protocole (`HouseProtocolForm.jsx`), utilisé à l'étape 1
de l'assistant de création de ferme et pour modifier le protocole d'un bâtiment
existant depuis `/dashboard/houses/{houseCode}/protocol`. Un résumé de cette page
est aussi accessible directement dans l'application via le bouton « ? » du même
écran — ce document va plus loin.

## À quoi sert le protocole

Le protocole d'un bâtiment (`ProtocolTemplate`) est un ensemble de lignes de
référence — « quoi faire, et quand » — organisées par catégorie
(`ProtocolCategory`). Chaque ligne définit une plage (De / À, en jours, semaines
ou mois depuis le début de la bande, ou « jusqu'à la fin de cycle »), une action
courte et un détail libre.

Le protocole est attaché au **bâtiment**, pas à une bande précise : il sert de
modèle réutilisé pour chaque nouvelle bande démarrée dans ce bâtiment, jusqu'à ce
qu'il soit modifié. Démarrer une bande ne copie pas les lignes ailleurs — l'écran
de suivi quotidien les affiche directement depuis le bâtiment.

**Écart entre le cahier des charges et le code, à noter :** le cahier des
charges section 4.6 documente l'intention suivante pour `ProtocolTemplate` :
« Étendu en lignes `AlertRule` à la création d'une bande, décalées par rapport
à `PoultryBatch.startDate` » — chaque ligne de protocole (une vaccination à J+1,
par exemple) devrait générer un rappel automatique au bon moment du cycle de la
bande. **Cette fonctionnalité n'est pas implémentée** : aucun chemin de code ne
crée de ligne `AlertRule` à partir de `ProtocolTemplate` ni au démarrage d'une
bande (vérifié avant d'écrire cette documentation, pour ne pas décrire une
fonctionnalité qui n'existe pas). Les types d'alerte `VACCINE_DUE` et
`SANITARY_VOID_END` existent dans le schéma (`AlertRuleType`) mais ne sont
déclenchés par aucun code — voir `docs/deviations.md` #16, qui documentait déjà
cet écart avant cette passe. Le protocole reste, pour l'instant, un aide-mémoire
consulté par les utilisateurs (Fermier/Ouvrier), pas un système de rappels
automatiques — un chantier futur, pas une régression introduite ici.

## Les 5 catégories par défaut

Créées automatiquement pour chaque nouveau bâtiment (`apps.houses.signals`, à la
création du `PoultryHouse`) — ce sont des lignes de structure vides (aucune ligne
de protocole), pas des données d'exemple, donc leur création automatique ne viole
pas la règle « pas de données par défaut » du projet.

| Catégorie | Icône | Contenu typique |
|---|---|---|
| Alimentation | `Soup` | Type d'aliment par phase (démarrage/croissance/finition), composition |
| Température | `Thermometer` | Consignes de chauffage/éleveuse par âge, seuils de la salle |
| Santé et soins | `Stethoscope` | Traitements préventifs, vitamines, antiparasitaires |
| Vaccination | `Syringe` | Vaccin, souche, voie d'administration, âge |
| Nettoyage | `SprayCan` | Litière, désinfection, fréquence |

## Catégories personnalisées

Le bouton « + » à droite des onglets ouvre un petit formulaire en ligne (pas une
fenêtre modale) : un nom et une icône, choisie parmi une liste courte de 12
icônes adaptées à l'élevage — voir `apps/protocols/models.py`
(`CUSTOM_CATEGORY_ICON_CHOICES`) côté backend et `ICON_OPTIONS` dans
`HouseProtocolForm.jsx` côté frontend (les deux listes sont tenues synchronisées
à la main, pas partagées automatiquement — à surveiller si l'une change sans
l'autre).

- **Pendant la création de la ferme (onboarding) :** une catégorie ajoutée reste
  en mémoire locale jusqu'à la validation de l'étape — le bâtiment n'existe pas
  encore côté serveur, donc rien n'est enregistré ligne par ligne. Les lignes de
  protocole référencent leur catégorie par position (`categoryIndex`) dans la
  requête envoyée à `POST /api/protocols/onboarding/` : 0-4 pour les 5 catégories
  par défaut (dans leur ordre fixe), 5+ pour les catégories personnalisées, dans
  l'ordre où elles ont été ajoutées.
- **En modification (bâtiment déjà existant) :** l'ajout est enregistré
  immédiatement via `POST /api/houses/{houseCode}/protocol-categories/`
  (interface optimiste : l'onglet apparaît avant la confirmation du serveur,
  puis se met à jour ou disparaît si l'enregistrement échoue).

### Suppression d'une catégorie

Un contrôle (icône ×) apparaît au survol de l'onglet, **en mode gestion
uniquement** — pas pendant l'assistant de création. Décision délibérée : pendant
l'assistant, les 5 catégories par défaut occupent toujours exactement les
positions 0 à 4 du tableau local, ce qui est ce qui permet de résoudre
`categoryIndex` côté serveur avant qu'aucune catégorie n'ait d'identifiant réel.
Supprimer une catégorie par défaut à ce stade casserait cet alignement. Une fois
le bâtiment créé, chaque catégorie a un identifiant réel et la suppression n'a
plus cette contrainte.

Supprimer une catégorie supprime aussi **toutes ses lignes de protocole**
(`ProtocolTemplate.category` est `on_delete=CASCADE`) — une confirmation
explicite le rappelle avant toute suppression, catégorie par défaut ou
personnalisée.

## Nom de la bande

Depuis cette mise à jour, démarrer une bande depuis l'écran de protocole demande
un nom (« Nom de la bande », ex. « Bande printemps 2026 »), enregistré comme
`PoultryBatch.name`. Ce nom devient le libellé principal utilisé partout où une
bande est affichée (vue par bâtiment) — le code système (`batchCode`, ex.
`BATCH-2026-001`) reste visible en complément, pas comme identifiant principal.

Le champ n'est **exigé** que dans l'assistant de création (une bande y est
toujours démarrée). En modification du protocole d'un bâtiment existant, le champ
reste affiché par cohérence avec les trois autres champs de l'en-tête, mais
— comme ces trois autres champs déjà avant cette mise à jour — n'est pas
persisté par cet écran, qui n'enregistre que les lignes de protocole
(`PUT /api/houses/{houseCode}/protocol/`). Renommer une bande existante n'est pas
une fonctionnalité de cet écran.

## Voir aussi

- `docs/data-model.md` — modèle de données complet (à rafraîchir : ce document
  décrit encore l'ancien enum `ProtocolCategory` à cinq valeurs fixes ; non mis à
  jour dans cette passe, hors du périmètre demandé).
- `winchicken-cahier-des-charges.docx` section 4.6 et
  `winchicken-spec-implementation-detaillee.docx` section 3.1 — mises à jour dans
  cette même passe pour refléter les catégories dynamiques.
