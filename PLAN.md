# PLAN — lifelog-mcp

Serveur MCP personnel de journalisation (habitudes, santé…), utilisable comme connecteur
personnalisé claude.ai. L'API REST en lecture prévue au départ est abandonnée (D65). Voir [INTENT.md](INTENT.md) pour la
demande complète.

## Étapes

Légende : ⬜ à faire · 🟨 en cours · ✅ terminée (commitée) · ❌ abandonnée

| # | Étape | Statut |
|---|---|---|
| 1 | Squelette local exécutable de bout en bout | ✅ |
| 2 | Infra Azure + authentification Entra (levée du risque OAuth) | ✅ |
| 3 | Modèle générique et catégorie `drinks` (logique pure) | ✅ |
| 4 | Stockage : interface `Repository`, mémoire et Table Storage | ✅ |
| 5 | Outils MCP métier | ✅ |
| 6 | ~~API REST en lecture~~ (D65) | ❌ |
| 7 | CI/CD GitHub Actions | ✅ |
| 8 | Finitions : README portfolio, sobriété des logs, revue des coûts | ⬜ |

Chaque étape = une proposition détaillée validée, une exécution vérifiée, une revue, puis
un commit sur demande.

### Prérequis (hors commit, avant l'étape 2)
- Créer un compte Azure (compte Microsoft personnel) et un abonnement.
- Outils locaux : `uv`, Docker, Azure CLI (`az`), Terraform, Node (pour MCP Inspector).

### 1. Squelette local exécutable de bout en bout
But : une app qui démarre en local et en conteneur, sur laquelle un client MCP se connecte.
Aucune fonctionnalité métier.
- Projet `uv`, Python 3.13, layout `src/lifelog/`, `ruff`, `pytest`.
- App FastAPI avec FastMCP monté sur `/mcp` (transport HTTP), un outil factice `ping`.
- Configuration par variables d'environnement (`pydantic-settings`).
- Tests : appel de `ping` via le client MCP en mémoire de FastMCP, démarrage de l'app.
- `Dockerfile` (image légère, utilisateur non root) ; vérification avec `docker run` et
  MCP Inspector.
- README minimal (lancer, tester).

### 2. Infra Azure + authentification Entra (levée du risque OAuth)
But : prouver tôt que claude.ai (web puis iPhone) se connecte au serveur via Entra, avec
seulement l'outil `ping`.
- Code :
  - `LIFELOG_AUTH` = `entra` (défaut) ou `none` (dev local) ; config Entra incomplète en
    mode `entra` → l'app refuse de démarrer (D31).
  - `AzureProvider` de FastMCP (proxy OAuth) : tenant unique, scope `access`, écran de
    consentement conservé, URI de redirection des clients limitées (D35).
  - Liste blanche des `oid` autorisés, appliquée par un middleware HTTP (D32).
  - État OAuth dans Azure Table Storage via l'identité managée, chiffré par nous (D30) ;
    en mémoire en local. Clé de signature fixe (D14).
  - Tests : `/mcp` sans jeton → 401 ; `oid` hors liste refusé, `oid` autorisé accepté ;
    `/.well-known/...` publics ; `/docs` & co toujours 404 ; démarrage refusé si config
    incomplète.
- `infra/bootstrap/` : groupe de ressources `rg-lifelog` + compte de stockage
  pour l'état Terraform distant.
- `infra/` (état distant), région `canadacentral` (D28) :
  - environnement Container Apps (sans Log Analytics) ; Container App (scale 0 → 1, image
    ghcr.io publique, port 8000, sonde TCP, identité managée) ;
  - inscription d'application Entra (`azuread`) : scope `access`, redirection
    `https://<fqdn>/auth/callback`, secret client valide 1 an ;
  - compte de stockage dédié + table de l'état OAuth, rôle « Storage Table Data
    Contributor » pour l'identité managée ;
  - secrets de la Container App (secret client, clé de signature, clé de chiffrement),
    générés par Terraform (D34) ;
  - alerte de budget sur l'abonnement (D29).
  - URL publique calculée à partir du nom de l'app et du domaine de l'environnement (D33).
- Image construite et poussée à la main sur ghcr.io pour cette étape, avec
  `--platform linux/amd64` (le Mac est en arm64, Container Apps exécute de l'amd64).
- Vérification réelle : connecteur ajouté sur claude.ai, `ping` appelé depuis le web et
  depuis l'iPhone ; un autre compte est refusé.
- Risque principal : connexion d'un compte Microsoft personnel à une app à tenant unique
  (D13). Repli : `tenant_id="consumers"`, la liste blanche restant en place.
- Résultat : connexion Entra et `ping` réussis depuis le web et l'iPhone avec le compte
  personnel invité du tenant (D13 confirmée, repli inutile). Refus d'un autre compte non
  testé en réel : couvert par les tests automatiques (liste blanche) et par l'assignation
  obligatoire de l'app Entra (D37). Démarrage à froid parfois trop lent pour la
  vérification de claude.ai (D36).

### 3. Modèle générique et catégorie `drinks` (logique pure)
- Modèle `Entry` (catégorie, horodatage, quantité, note, attributs) — `entries.py`.
- Contrat d'une catégorie : nom, description, modèle Pydantic des attributs (validation),
  calcul des stats ; registre des catégories (objet instanciable, D46) — `categories/`.
- Catégorie `drinks` : types `beer`, `cider`, `wine`, `spirits`, `other` (D39), valeurs par
  défaut appliquées et stockées (D40), verres standard recalculés à la lecture (D41).
  Stats : total, nombre d'entrées, verres par semaine ISO (semaines vides incluses), jours
  sans entrée.
- Utilitaires de temps (heure de Québec D47, périodes D44, semaines ISO, jours sans
  entrée) — `timeutils.py`.
- Tests : calcul des verres standard, validation, stats, bornes de dates, catégorie fictive
  ajoutée dans les tests sans rien toucher d'autre.

### 4. Stockage : interface `Repository`, mémoire et Table Storage
- Interface `Repository` : `add_many` (tout ou rien, une catégorie) et `list` (catégorie,
  intervalle UTC, tri par heure) — `storage/`.
- Implémentation en mémoire (tests, dev local) et implémentation Azure Table Storage
  (identité managée) : table `entries`, `PartitionKey` = catégorie, `RowKey` = heure au
  format fixe + identifiant (D57), écriture en lot transactionnelle, attributs en JSON.
- Couche service (`log_entries`, `list_entries`, `get_stats`, `list_categories`) partagée
  par les outils MCP — `service.py`. Validation de tout le lot avant écriture, erreurs
  numérotées.
- `LIFELOG_STORAGE` = `table` (défaut) ou `memory` ; `LIFELOG_TABLE_ACCOUNT` obligatoire
  en mode `table` (D51).
- Terraform : compte de stockage dédié aux données, table `entries`, verrou contre la
  suppression (D58) ; droits sur les tables pour l'app et l'utilisateur (D53).
- Tests : un même jeu de tests pour les deux stockages ; service sur le stockage en
  mémoire ; tests réels à la demande (marqueur `azure`, D52).
- Essai Cosmos DB abandonné : création refusée faute de capacité (D56).
- L'image déployée n'est pas mise à jour à cette étape : rien ne l'utilise avant les
  outils de l'étape 5.

### 5. Outils MCP métier
- `log_entry`, `list_entries`, `get_stats`, `list_categories` ; retrait de `ping`. Outils
  minces au-dessus du service — `mcp_server.py`.
- Catégories en liste fermée dans les schémas (D59) ; heures en UTC en entrée et en sortie
  (D60) ; erreurs de validation transmises, erreurs inattendues masquées (D61).
- Descriptions pensées pour relier une phrase en français à la bonne catégorie : la
  description de `log_entry` reprend celle de chaque catégorie et le schéma de ses
  attributs, pour enregistrer sans appel préalable à `list_categories`.
- Tests via le client MCP en mémoire, dont la catégorie fictive proposée sans toucher aux
  outils.
- Déploiement et vérification des critères de réussite depuis l'iPhone.
- Import de l'historique Todoist par Cowork, sans code dédié (D62).
- Premier essai sur l'iPhone : Claude a repris le volume et le taux d'une entrée
  précédente au lieu de les demander, puis proposé une correction impossible. Consigne
  renforcée (D63).
- Résultat : depuis l'iPhone, « ajoute 2 bières » fait demander le volume et le taux,
  « la même que tantôt » reprend les valeurs, une correction est refusée, et le total de
  la semaine est juste. claude.ai gardait les anciennes descriptions des outils jusqu'à la
  reconnexion du connecteur (D64).

### 6. ~~API REST en lecture~~ — abandonnée (D65)
Prévue au départ : `GET /api/categories`, `/api/entries`, `/api/stats`, authentification
par jeton Bearer Entra et même liste blanche. Les données sont lues par des agents Claude
(dashboard hebdomadaire), qui passent par les outils MCP.

### 7. CI/CD GitHub Actions
- Un workflow `.github/workflows/ci-cd.yml` : `test` (`ruff check`, `ruff format --check`,
  `pytest`) sur chaque PR et push ; sur `main`, `build` (image `linux/amd64` poussée sur
  ghcr.io avec le `GITHUB_TOKEN`, étiquettes `sha-<commit>` et `latest`) puis `deploy`.
- `deploy` : connexion OIDC à Azure, `az containerapp update --image`, puis vérification
  que `/mcp` répond 401 (attente du démarrage à froid).
- Terraform (`infra/cicd.tf`) : identité managée `id-lifelog-github`, identité fédérée sur
  l'environnement GitHub `production`, rôle « Container Apps Contributor » sur la seule
  Container App (D67, D68) ; image ignorée après la création (D66).
- Variables de dépôt `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
- Actions épinglées par SHA, Dependabot mensuel (D69).
- Premier passage : push refusé tant que le dépôt n'avait pas l'accès en écriture au
  package (créé à la main) ; connexion Azure refusée avec le sujet OIDC classique (D70).

### 8. Finitions
- README portfolio : architecture, lancer, tester, design des outils MCP, décisions, ce
  qu'on ferait avec plus de temps (dont l'API REST, D65).
- Revue des logs (niveau, contenu sans données personnelles) et des coûts.
- Démarrage à froid (D36) : mesurer, puis allonger le délai de mise en veille et/ou
  accélérer le démarrage.
- Sauvegarde des entrées (D58) : export régulier de la table vers un blob versionné.
- Refactorisation : retirer FastAPI, qui n'héberge plus que l'app MCP depuis l'abandon de
  l'API REST (D65). L'app Starlette de FastMCP suffit ; déploiement par la CI/CD de
  l'étape 7.

## Journal des décisions

**D1 — Base de données : Azure Table Storage** (d'abord Cosmos DB NoSQL, voir D56).
Les attributs varient selon la catégorie : un stockage NoSQL s'y prête mieux qu'un schéma
relationnel. Azure SQL en pause automatique a un réveil d'environ une minute, mauvais pour
un usage en conversation. Cosmos DB (volet gratuit) était le premier choix ; sa création
a été refusée faute de capacité, et Table Storage couvre aussi bien le besoin (D56).

**D2 — Accès aux données via une interface `Repository`.**
Une implémentation en mémoire (tests, dev local sans Azure) et une implémentation Cosmos.
Tests Cosmos DB sur la vraie base plutôt que l'émulateur (D52).

**D3 — `quantity` = nombre de contenants.**
Le volume et le % d'alcool s'appliquent à un contenant ; total = quantité × verres par
contenant.

**D4 — Volume et % d'alcool selon le type.**
Bière et « autre » : volume (ml) et % obligatoires, car très variables (le volume et le %
sont fournis d'un trait dans le message). Vin : 142 ml à 12 % par défaut. Spiritueux :
43 ml à 40 % par défaut. Les valeurs par défaut peuvent être remplacées.
Verres standard = `ml × %/100 × 0,789 g/ml ÷ 13,45 g`. Si une bière arrive sans ces
informations, la validation refuse avec un message explicite et Claude les demande ; Claude
ne devine pas le % d'une marque.

**D5 — Semaine ISO (lundi–dimanche), jour calendaire minuit–minuit à Québec.**
Simple et prévisible ; une entrée à 0 h 30 compte pour le jour suivant.

**D6 — « Jours sans entrée » = jours de la période sans aucune entrée, jusqu'à aujourd'hui
inclus.** Les jours futurs ne comptent pas.

**D7 — Période : `start`/`end` optionnels, semaine en cours par défaut.**
Claude convertit les expressions (« ce mois-ci ») en dates.

**D8 — Heures stockées en UTC ; jours et semaines en heure de Québec.** Dans le code,
une heure sans fuseau est l'heure de Québec. Les outils reçoivent et renvoient de l'UTC
(D60).

**D9 — `log_entry` accepte une liste d'entrées d'une même catégorie, validée en entier
avant écriture (tout ou rien).**

**D10 — Pas de `delete_entry` ni de modification pour l'instant.** Hors de la demande ;
candidat pour plus tard. Les instructions du serveur le disent à Claude, pour qu'il ne
propose pas de correction impossible (D63) ; une erreur se corrige dans le portail Azure.

**D11 — Noms et descriptions d'outils en anglais, avec des exemples en français.**
Convention du code en anglais ; l'utilisateur converse en français et Claude fait le lien
grâce aux exemples (« bière », « verre de vin », « shooter », « ce soir »).

**D12 — *(abandonnée, voir D65)* API REST : `GET /api/categories`, `/api/entries`, `/api/stats` avec paramètres
`category`, `start`, `end`.**

**D13 — Un seul utilisateur : app Entra limitée au tenant de l'abonnement + liste blanche
de l'identifiant (`oid`) côté serveur.** L'utilisateur se connecte avec un compte Microsoft
personnel (invité du tenant par défaut) ; à confirmer à l'étape 2. L'API REST prévue
devait valider les jetons Entra avec la même liste blanche (abandonnée, D65).

**D14 — État OAuth persistant.**
Le proxy OAuth de FastMCP garde les clients enregistrés et les jetons ; en mémoire, ils
seraient perdus à chaque scale à zéro (reconnexion forcée). Le stockage persistant et une
clé de signature fixe (secret) seront choisis à l'étape 2.

**D15 — État Terraform distant amorcé par `infra/bootstrap/`.** Premier `apply` avec un
état local (le compte de stockage n'existe pas encore), puis état du bootstrap migré dans
ce même compte (`bootstrap.tfstate`) : aucune copie locale à sauvegarder, versions
conservées par le stockage. Seul inconvénient : détruire le bootstrap supprimerait son
propre état, ce qui n'arrive qu'en démontant tout le projet.

**D16 — CI/CD : OIDC vers Azure, image ghcr.io publique, `terraform apply` manuel au début.**
OIDC évite de stocker un secret Azure dans GitHub ; l'image ne contient aucune donnée.

**D17 — Outils Python : `uv`, Python 3.13, `pytest`, `ruff`.**

**D18 — INTENT.md et PLAN.md versionnés dans le dépôt.**
Ils montrent la démarche. Aucune donnée réelle dans le dépôt (ni seed, ni exemples tirés
des données).

**D19 — URL par défaut de Container Apps, pas de domaine personnalisé.**

**D20 — Aucun endpoint public hors MCP : pas de `/health`, et `/docs`, `/redoc`,
`/openapi.json` de FastAPI désactivés.** Ils seraient accessibles sans authentification.
Container Apps vérifie le conteneur par une sonde TCP. Seuls les endpoints de découverte
OAuth (`/.well-known/...`) seront publics à l'étape 2, comme l'exige le protocole.
Un test vérifie que ces routes renvoient 404.

**D21 — FastMCP 4.x (4.1.4 à l'installation), versions figées dans `uv.lock`.**

**D22 — MCP Inspector lancé via `npx`, sans dépendance dans le projet.**

**D23 — L'app MCP est montée à la racine de FastAPI (`app.mount("/", ...)`), et sert
elle-même `/mcp`.** Monter sur `/mcp` aurait donné `/mcp/mcp` ou une redirection, et les
routes OAuth de l'étape 2 doivent être à la racine. Les routes FastAPI (`/api/...`)
déclarées avant le montage restent prioritaires.

**D24 — Application construite par une fonction `create_app(settings)` (« factory »).**
Les tests créent une app isolée avec leur propre configuration ; Uvicorn l'appelle avec
`--factory`.

**D25 — Tests asynchrones avec `pytest-asyncio` (mode auto) ; tests HTTP en processus via
les utilitaires de FastMCP (`ASGIServer`, `run_asgi_lifespan`)**, sans port ni Uvicorn.

**D26 — Image Docker en deux étapes (build avec `uv`, exécution sur `python:3.13-slim`),
utilisateur non root, port 8000.**

**D27 — Le dépôt ne vit pas dans un dossier synchronisé par iCloud Drive.** iCloud marque
des fichiers comme cachés ; Python 3.13 ignore les fichiers `.pth` cachés, et le paquet
installé en mode éditable devient introuvable. iCloud crée aussi des doublons de conflit
(« .venv 2 »). GitHub sert de sauvegarde.

**D28 — Région Azure : `canadacentral` (centre de données à Toronto).** Proche de l'utilisateur ; Container
Apps et Cosmos DB y sont disponibles.

**D29 — Alerte de budget à 5 $ par mois sur l'abonnement.** Le courriel de destination est
une variable Terraform, hors du dépôt.

**D30 — État OAuth dans Azure Table Storage, accédé par l'identité managée de la Container
App.** Simple base clé-valeur, déjà prise en charge par `py-key-value` (utilisé par
FastMCP), coût négligeable, aucun secret de stockage. FastMCP ne chiffre que son stockage
par défaut : on enveloppe la table dans `FernetEncryptionWrapper` avec une clé dédiée.
Les clés interdites par Azure Tables (`/`, `?`… dans les identifiants de clients en URL)
sont remplacées par une empreinte (`AzureTablesSanitizationStrategy`). Le module Azure
Tables est marqué « instable » par la librairie : versions figées dans `uv.lock`, à
revérifier lors des mises à jour.
Écartés : Cosmos DB (aucun module existant, mélange avec les données), Azure Files
(accès concurrent fragile, clé de stockage), Redis (≈ 15 $/mois).

**D31 — `LIFELOG_AUTH=entra` par défaut ; `none` seulement sur demande explicite.** Une
config Entra incomplète fait échouer le démarrage : impossible de déployer sans
authentification par oubli.

**D32 — Liste blanche par `oid` dans un middleware HTTP (Starlette)**, placé juste après
la validation du jeton : toute requête authentifiée d'un `oid` hors liste reçoit 403,
avant même le protocole MCP. Plus net qu'un filtrage outil par outil, et réutilisable
pour l'API REST. Le tenant unique est une première barrière, la liste blanche la seconde.

**D33 — URL publique calculée (`<nom de l'app>.<domaine de l'environnement>`)** plutôt que
lue sur la Container App : l'inscription Entra et les variables de l'app en ont besoin,
ce qui créerait une dépendance circulaire dans Terraform.

**D34 — Secrets générés par Terraform (secret client, clé de signature, clé de
chiffrement).** Ils figurent dans l'état Terraform, conservé dans un compte de stockage
privé : acceptable pour un projet personnel.

**D35 — URI de redirection des clients MCP limitées au callback de claude.ai et à
`localhost` (MCP Inspector).**

**D36 — Scale à zéro conservé malgré le démarrage à froid.** Après une longue
inactivité, la vérification du connecteur par claude.ai a expiré pendant le réveil du
conteneur ; un nouvel essai, conteneur réveillé, a réussi. Toujours allumé
(`min_replicas = 1`) : ≈ 5,70 $ US/mois au tarif inactif après la part gratuite, au-delà
du budget (D29). Pistes pour l'étape 8 : délai de mise en veille de 30 à 60 min (coût
seulement pendant les sessions), image et démarrage plus rapides.

**D37 — App Entra à assignation obligatoire (`app_role_assignment_required`)**, avec les
`oid` de la liste blanche assignés par Terraform. Un compte non assigné est refusé par
Entra dès la connexion, avant la liste blanche du serveur (D32).

**D38 — *(remplacée par l'étape 7)* Push manuel sur ghcr.io avec un jeton d'accès personnel classique**
(`write:packages`, expiration courte, révoqué après usage) : ghcr.io refuse le jeton OAuth
de GitHub CLI. À l'étape 7, GitHub Actions utilisera son `GITHUB_TOKEN`.

**D39 — Type de boisson `cider` : 5 % d'alcool par défaut, volume obligatoire.** Les
formats de cidre varient trop (355, 473, 500 ml…) pour un volume par défaut ; le taux,
lui, est assez stable. Complète D4.

**D40 — Les attributs stockés sont les valeurs appliquées (défauts inclus).** Un vin
sans précision est stocké à 142 ml et 12 % : changer un jour les valeurs par défaut ne
modifie pas l'historique.

**D41 — Verres standard recalculés à la lecture, jamais stockés.** Le volume et le taux
suffisent ; une seule source de vérité.

**D42 — Quantité décimale strictement positive** (« un demi-verre » = 0,5).

**D43 — Bornes : volume de 1 à 5 000 ml, taux de 0 à 100 %.** 0 % permet la bière sans
alcool (0 verre standard).

**D44 — Période : début seul → jusqu'à aujourd'hui ; fin seule → refusée (ambiguë).**
Complète D7.

**D45 — Stats calculées en pleine précision, arrondies à 1 décimale dans le résultat ;
pas de répartition par type pour l'instant** (hors de la demande).

**D46 — Registre des catégories instanciable**, plutôt qu'un dictionnaire global : les
tests construisent leur propre registre (avec une catégorie fictive) sans toucher au
registre réel. Les modèles d'attributs refusent les champs inconnus (une faute de frappe
devient une erreur, pas une donnée perdue).

**D47 — Heure de Québec, identifiant technique `America/Toronto`.** L'utilisateur habite
Québec : les textes, la doc et le code parlent d'heure de Québec. La base IANA des fuseaux
n'a pas d'entrée `America/Quebec` ; Québec y relève du fuseau de l'Est, dont la ville de
référence est Toronto (`America/Montreal` n'est qu'un alias obsolète). L'identifiant
n'apparaît qu'à un seul endroit du code, commenté.

**D48 — *(remplacée par D56)* Cosmos DB : une collection `entries`, clé de partition `/category`.** Les
requêtes d'une catégorie restent dans une partition, et un lot (une seule catégorie, D9)
s'écrit en une transaction. Limite de 20 Go par partition : très loin pour un journal
personnel.

**D49 — *(reprise par D57)* Heure stockée au format ISO de longueur fixe, avec microsecondes
(`2026-11-04T01:00:00.000000Z`).** Cosmos compare les dates comme du texte : un format
variable trierait mal deux entrées dans la même seconde.

**D50 — *(remplacée par D56)* Compte Cosmos DB : volet gratuit, clés désactivées, sauvegarde continue 7 jours,
base à 400 RU/s partagées.** Le volet gratuit (1 000 RU/s, 25 Go) ne s'active qu'à la
création et pour un seul compte par abonnement. La sauvegarde continue 7 jours est
gratuite et permet une restauration à n'importe quel moment de la semaine.

**D51 — `LIFELOG_STORAGE=cosmos` (devenu `table`, D56) par défaut ; `memory` seulement sur demande.** Même
principe que D31 : un oubli de configuration ne doit pas faire tourner la production en
mémoire et perdre des données.

**D52 — Tests sur le vrai stockage Azure, à la demande (marqueur pytest `cosmos`, devenu `azure`).**
L'émulateur n'accepte pas l'authentification par identité et sa version pour Mac est en
préversion. Ces tests ne tournent ni par défaut, ni dans la CI. Remplace l'émulateur
optionnel de D2.

**D53 — Accès aux données (Cosmos DB, puis Table Storage) pour l'app (identité managée) et pour l'utilisateur**
(portail Azure, tests réels depuis le Mac).

**D54 — *(remplacée par D56)* Compte Cosmos DB propre à lifelog, non partagé ; droits limités à la base
`lifelog`.** Un compte partagé entre projets garderait le volet gratuit pour tous, mais
deviendrait un prérequis extérieur au dépôt et lierait les projets entre eux. Un autre
petit projet peut utiliser Cosmos DB en mode serverless (quelques cents par mois) ou un
autre abonnement (son propre volet gratuit).

**D55 — *(remplacée par D56)* Compte Cosmos DB dans `canadaeast` (Québec), le reste dans `canadacentral`.**
La création a été refusée en Canada Central (« high demand », fréquent pour les
abonnements récents). Coût : environ 10 ms de plus par requête et un trafic entre
régions quasi nul (≈ 0,02 $ US/Go). Les données restent au Canada. Container Apps et
Storage existent aussi en Canada East : tout pourra y être regroupé plus tard
(variable `cosmos_location`, puis recréation de l'app et du stockage OAuth).

**D56 — Stockage des entrées dans Azure Table Storage au lieu de Cosmos DB.** La création
du compte Cosmos DB a été refusée en Canada Central puis en Canada East (« high demand »,
fréquent pour les abonnements récents). Table Storage couvre exactement le besoin :
partition par catégorie, lecture d'une période par intervalle de clés, lot transactionnel
(100 entrées, même partition), identité managée, coût de quelques cents. Déjà utilisé
pour l'état OAuth, sans contrainte de capacité. Limites acceptées : attributs stockés en
JSON (jamais filtrés), pas de restauration à un instant passé (D58). L'interface
`Repository` a rendu la bascule locale au stockage. Remplace D48, D50, D54 et D55.

**D57 — Clé de ligne = heure UTC au format fixe + identifiant
(`2026-11-04T01:00:00.000000Z_<uuid>`).** Une période se lit avec un intervalle de
`RowKey` dans une partition, résultats déjà triés ; l'identifiant départage deux entrées
à la même microseconde. Reprend D49.

**D58 — Compte de stockage dédié aux données, avec verrou contre la suppression
(« CanNotDelete »).** Trois comptes au total (état Terraform, état OAuth jetable,
données précieuses) : aucun coût fixe, un rôle évident chacun. Pas de restauration à un
instant passé dans Table Storage : un export régulier vers un blob versionné est prévu
à l'étape 8.

**D59 — Catégories en liste fermée dans le schéma des outils** (`enum`, ou `const` tant
qu'il n'y en a qu'une), construite à partir du registre. Claude voit les valeurs
possibles et ne peut pas en inventer ; une nouvelle catégorie s'y ajoute sans toucher aux
outils.

**D60 — Heures des outils en UTC, en entrée comme en sortie.** L'utilisateur peut être
hors de Québec : Claude convertit depuis le fuseau où il se trouve, et une heure sans
fuseau ou avec un autre décalage est refusée plutôt que devinée. Sans heure, l'entrée
prend l'heure du serveur. Les jours, semaines et dates `start`/`end` restent ceux de
Québec (D5) : des stats stables, peu importe où on les consulte. Remplace la partie
« réponses en heure de Québec » de D8.

**D61 — Erreurs : validation transmise telle quelle, le reste masqué.** Lot invalide,
période refusée ou catégorie inconnue : le message part vers Claude, qui corrige ou pose
la question. Toute autre erreur (stockage, réseau…) arrive comme un message générique ;
le détail reste dans les logs (`mask_error_details` de FastMCP).

**D62 — Historique Todoist importé par Cowork, sans code dédié.** Environ 50 entrées :
Cowork les lit avec le connecteur Todoist, les convertit en UTC et les envoie avec
`log_entry` (un ou deux lots). INTENT.md classait la migration hors portée parce qu'elle
aurait demandé du code ; ce n'est plus le cas.

**D63 — Claude n'envoie que les attributs donnés par l'utilisateur.** Le serveur ne peut
pas distinguer une valeur dite d'une valeur reprise d'une entrée précédente : les
instructions du serveur et la description de `log_entry` interdisent de réutiliser des
valeurs (sauf « la même », « pareil ») et de deviner. Un champ laissé vide déclenche le
refus qui dit quoi demander (D4). Elles disent aussi qu'une entrée ne peut pas être
corrigée (D10). Une consigne, pas une garantie : à revoir si l'essai réel montre que ça
ne suffit pas.

**D64 — Après un changement des descriptions d'outils ou des instructions du serveur,
reconnecter le connecteur claude.ai.** claude.ai garde une copie de la liste des outils,
même dans une nouvelle conversation : le serveur n'a reçu aucune demande de liste après
le déploiement, et Claude citait l'ancienne description. La reconnexion force la
relecture.

**D65 — Pas d'API REST : l'étape 6 est abandonnée.** Les données sont lues par Claude :
en conversation, et chaque semaine par l'agent personnel qui construit le dashboard santé.
Cet agent utilise le connecteur lifelog comme l'app iPhone ; les outils renvoient du JSON
structuré (`get_stats`, `list_entries`), sans interprétation de texte. Une API REST
n'aurait aucun utilisateur et ajouterait un second point d'entrée authentifié à protéger
et à tester. INTENT.md la demandait pour un dashboard ; ce choix est assumé. Pour plus
tard, si un programme sans Claude doit lire les données (page web, script, raccourci
iOS) : le service est déjà indépendant de MCP, l'API s'ajouterait sans toucher à
l'existant. FastAPI, qui n'héberge plus que l'app MCP, sera retiré à l'étape 8. Remplace D12.

**D66 — Le déploiement change seulement l'image ; Terraform l'ignore après la création.**
GitHub Actions fait `az containerapp update --image`, et la Container App porte
`ignore_changes` sur l'image : un `terraform apply` ne revient pas à `var.image`, qui ne
sert plus qu'à la première création. Écarté : `terraform apply` dans la CI, qui
demanderait l'accès à l'état (avec ses secrets) et des droits sur Entra pour changer une
image.

**D67 — Identité de déploiement : identité managée « utilisateur » à identité fédérée,
rôle « Container Apps Contributor » sur la seule Container App.** Aucun secret dans
GitHub (OIDC) ; l'identité ne peut toucher ni au stockage, ni à Entra. Écarté : une
inscription d'application Entra, en double avec celle de l'app.

**D68 — Environnement GitHub `production` pour la tâche `deploy`.** L'identité fédérée
ne fait confiance qu'à cet environnement du dépôt : une PR, un fork ou une autre branche
ne peut pas déployer. Une approbation manuelle pourra s'y ajouter sans autre changement.

**D69 — Actions épinglées par SHA, Dependabot mensuel** (actions, images Docker de base,
dépendances `uv`, une PR groupée par écosystème). Dépôt public : un SHA ne peut pas être
déplacé par un tiers, contrairement à une étiquette `v4`. Les PR de Dependabot passent
par la tâche `test`. Remplace l'image versionnée à la main (`0.2.0-dev.N`) par
l'étiquette du commit.

**D70 — Identité fédérée sur le sujet OIDC immuable de GitHub**
(`repo:SamuelPoirier-Dev@336244337/lifelog-mcp@1435982605:environment:production`). Les
dépôts récents envoient le nom accompagné des identifiants numériques du compte et du
dépôt ; le premier déploiement a échoué avec le format classique (`owner/name`). Plus
sûr : après un renommage, un autre compte qui reprendrait l'ancien nom n'obtiendrait pas
l'identité.
