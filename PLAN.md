# PLAN — lifelog-mcp

Serveur MCP personnel de journalisation (habitudes, santé…), utilisable comme connecteur
personnalisé claude.ai, avec une API REST en lecture. Voir [INTENT.md](INTENT.md) pour la
demande complète.

## Étapes

Légende : ⬜ à faire · 🟨 en cours · ✅ terminée (commitée)

| # | Étape | Statut |
|---|---|---|
| 1 | Squelette local exécutable de bout en bout | ✅ |
| 2 | Infra Azure + authentification Entra (levée du risque OAuth) | ⬜ |
| 3 | Modèle générique et catégorie `drinks` (logique pure) | ⬜ |
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
- `infra/bootstrap/` (état local) : groupe de ressources + compte de stockage pour l'état
  Terraform distant.
- `infra/` (état distant) : environnement Container Apps (sans Log Analytics), Container
  App (scale 0 → 1, image ghcr.io publique), inscription d'application Entra (`azuread`),
  secrets de la Container App, alerte de budget sur l'abonnement.
- `AzureProvider` de FastMCP (proxy OAuth) + liste blanche de l'utilisateur autorisé.
- Persistance de l'état OAuth (clients enregistrés, jetons) pour survivre au scale à zéro,
  et clé de signature fixe (voir D14).
- Image construite et poussée à la main sur ghcr.io pour cette étape, avec
  `--platform linux/amd64` (le Mac est en arm64, Container Apps exécute de l'amd64).
- Vérification réelle : connecteur ajouté sur claude.ai, `ping` appelé depuis le web et
  depuis l'iPhone ; un autre compte est refusé.

### 3. Modèle générique et catégorie `drinks` (logique pure)
- Modèle `Entry` (catégorie, horodatage, quantité, note, attributs).
- Contrat d'une catégorie : nom, description, modèle Pydantic des attributs (validation),
  calcul des stats ; registre des catégories.
- Catégorie `drinks` : types, valeurs par défaut, verres standard, stats.
- Utilitaires de temps (fuseau America/Toronto, semaines ISO, jours sans entrée).
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

**D5 — Semaine ISO (lundi–dimanche), jour calendaire minuit–minuit à Toronto.**
Simple et prévisible ; une entrée à 0 h 30 compte pour le jour suivant.

**D6 — « Jours sans entrée » = jours de la période sans aucune entrée, jusqu'à aujourd'hui
inclus.** Les jours futurs ne comptent pas.

**D7 — Période : `start`/`end` optionnels, semaine en cours par défaut.**
Claude convertit les expressions (« ce mois-ci ») en dates.

**D8 — Heures stockées en UTC ; heure sans fuseau = heure de Toronto ; réponses en heure
de Toronto.**

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

**D15 — État Terraform distant amorcé par `infra/bootstrap/` (état local).**

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

**D27 — Poste local : environnement virtuel dans `.venv.nosync`, avec un lien `.venv` vers
lui.** Le dépôt est dans iCloud Drive, qui marque des fichiers comme cachés ; Python 3.13
ignore les fichiers `.pth` cachés, et le paquet devient introuvable. Le suffixe `.nosync`
exclut aussi le dossier de la synchronisation. Ce réglage est propre à ce poste et n'est
pas versionné.
