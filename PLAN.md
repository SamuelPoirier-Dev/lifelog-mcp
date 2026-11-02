# PLAN — lifelog-mcp

Serveur MCP personnel de journalisation (habitudes, santé…), utilisable comme connecteur
personnalisé claude.ai, avec une API REST en lecture. Voir [INTENT.md](INTENT.md) pour la
demande complète.

## Étapes

Légende : ⬜ à faire · 🟨 en cours · ✅ terminée (commitée)

| # | Étape | Statut |
|---|---|---|
| 1 | Squelette local exécutable de bout en bout | ✅ |
| 2 | Infra Azure + authentification Entra (levée du risque OAuth) | ✅ |
| 3 | Modèle générique et catégorie `drinks` (logique pure) | ✅ |
| 4 | Stockage : interface `Repository`, mémoire et Cosmos DB | ⬜ |
| 5 | Outils MCP métier | ⬜ |
| 6 | API REST en lecture | ⬜ |
| 7 | CI/CD GitHub Actions | ⬜ |
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

### 4. Stockage : interface `Repository`, mémoire et Cosmos DB
- Interface `Repository` (ajout en lot, lecture par catégorie et période).
- Implémentation en mémoire (tests, dev local) et implémentation Cosmos DB.
- Couche service (`log_entries`, `list_entries`, `get_stats`, `list_categories`) partagée
  par MCP et REST.
- Terraform : compte Cosmos DB en volet gratuit, base, conteneur ; accès de la Container App.
- Tests du service sur le dépôt en mémoire ; test d'intégration Cosmos optionnel
  (émulateur), marqué pour ne pas tourner par défaut.

### 5. Outils MCP métier
- `log_entry`, `list_entries`, `get_stats`, `list_categories` ; retrait de `ping`.
- Descriptions pensées pour relier une phrase en français à la bonne catégorie.
- Tests via le client MCP en mémoire.
- Déploiement et vérification des critères de réussite depuis l'iPhone.

### 6. API REST en lecture
- `GET /api/categories`, `GET /api/entries`, `GET /api/stats`.
- Authentification par jeton Bearer Entra + même liste blanche.
- Tests (requêtes authentifiées, refus sans jeton ou avec un autre utilisateur).

### 7. CI/CD GitHub Actions
- CI sur PR et `main` : `ruff`, `pytest`.
- CD sur `main` : build, push ghcr.io, mise à jour de la Container App via OIDC
  (identité fédérée créée par Terraform).

### 8. Finitions
- README portfolio : architecture, lancer, tester, design de l'API, décisions, ce qu'on
  ferait avec plus de temps.
- Revue des logs (niveau, contenu sans données personnelles) et des coûts.
- Démarrage à froid (D36) : mesurer, puis allonger le délai de mise en veille et/ou
  accélérer le démarrage.

## Journal des décisions

**D1 — Base de données : Cosmos DB NoSQL, volet gratuit.**
Les attributs varient selon la catégorie : un document JSON s'y prête mieux qu'un schéma
relationnel. Azure SQL en pause automatique a un réveil d'environ une minute, mauvais pour
un usage en conversation. Le volet gratuit (1 000 RU/s, 25 Go) est disponible : aucun
compte Azure existant.

**D2 — Accès aux données via une interface `Repository`.**
Une implémentation en mémoire (tests, dev local sans Azure) et une implémentation Cosmos.
L'émulateur Cosmos reste optionnel.

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

**D8 — Heures stockées en UTC ; heure sans fuseau = heure de Québec ; réponses en heure
de Québec.**

**D9 — `log_entry` accepte une liste d'entrées d'une même catégorie, validée en entier
avant écriture (tout ou rien).**

**D10 — Pas de `delete_entry` pour l'instant.** Hors de la demande ; candidat pour plus tard.

**D11 — Noms et descriptions d'outils en anglais, avec des exemples en français.**
Convention du code en anglais ; l'utilisateur converse en français et Claude fait le lien
grâce aux exemples (« bière », « verre de vin », « shooter », « ce soir »).

**D12 — API REST : `GET /api/categories`, `/api/entries`, `/api/stats` avec paramètres
`category`, `start`, `end`.**

**D13 — Un seul utilisateur : app Entra limitée au tenant de l'abonnement + liste blanche
de l'identifiant (`oid`) côté serveur.** L'utilisateur se connecte avec un compte Microsoft
personnel (invité du tenant par défaut) ; à confirmer à l'étape 2. L'API REST valide les
jetons Entra avec la même liste blanche.

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

**D38 — Push manuel sur ghcr.io avec un jeton d'accès personnel classique**
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
