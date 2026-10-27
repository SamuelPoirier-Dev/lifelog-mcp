# INTENT — Serveur MCP de journal personnel

## Contexte
Je veux un serveur MCP personnel qui me sert de **point de départ pour journaliser
différentes choses de mon quotidien** (habitudes, santé…), directement en conversation
dans l'app Claude — sur iPhone surtout (ex. « 2 bières ce soir »). Les données sont
persistées dans le nuage et réutilisables par d'autres outils (dashboard santé).

**Premier cas d'usage : les consommations d'alcool**, que je note actuellement dans des
tâches Todoist (pas adapté). D'autres catégories viendront plus tard.

C'est aussi un projet de portfolio (back-end, cloud, IA) : la qualité du code, de l'infra
et du README compte autant que la fonctionnalité.

## Ce qu'il faut construire
Un serveur MCP distant, ajouté comme **connecteur personnalisé claude.ai** (utilisable sur
web, desktop et iOS).

### Modèle générique
- Une **entrée** (`entry`) appartient à une **catégorie** (`category`) et porte au minimum :
  date/heure, quantité, note optionnelle, et des attributs propres à la catégorie.
- Chaque catégorie définit ses attributs, sa validation et ses calculs.
- Ajouter une catégorie doit demander peu de code et ne pas toucher aux autres.
- Pas de sur-ingénierie : pas de catégories configurables à l'exécution ni de système de
  plugins ; une catégorie = un module de code.

### Outils MCP (génériques)
- `log_entry` : enregistre une ou plusieurs entrées dans une catégorie
  (date/heure par défaut : maintenant).
- `list_entries` : liste les entrées d'une catégorie sur une période.
- `get_stats` : statistiques d'une catégorie sur une période (agrégats propres à la catégorie).
- `list_categories` : catégories disponibles et leurs attributs (pour que Claude sache
  quoi demander).

Les descriptions des outils doivent permettre à Claude de faire le lien entre une phrase
naturelle (« 2 bières ce soir ») et la bonne catégorie.

### API REST
Sur la même logique métier, une **API REST en lecture** (`/api/entries`, `/api/stats`)
pour alimenter plus tard le dashboard.

### Première catégorie : `drinks`
- Attributs : type (bière, vin, spiritueux, autre), volume (ml) et % d'alcool optionnels.
- Calcul en **verres standard canadiens** (13,45 g d'alcool pur). Sans volume/% fournis,
  utiliser une valeur par défaut par type.
- Stats : verres standard par semaine, jours sans entrée.

### Général
- Fuseau horaire : America/Toronto.

## Stack imposée
| Rôle | Choix |
|---|---|
| Langage | Python |
| Serveur MCP | FastMCP (`fastmcp`), transport HTTP, endpoint `/mcp` |
| API REST | FastAPI (FastMCP monté dans l'app) |
| Serveur web | Uvicorn, conteneur Docker |
| Registre d'images | GitHub Container Registry (ghcr.io) |
| Hébergement | Azure Container Apps, plan Consumption (scale à zéro) |
| Base de données | Cosmos DB (volet gratuit) ou Azure SQL Database (offre gratuite) — à décider |
| Authentification | Microsoft Entra ID via `AzureProvider` de FastMCP (proxy OAuth) |
| IaC | Terraform (`azurerm` + `azuread`), état distant dans un compte de stockage Azure |
| CI/CD | GitHub Actions (souhaité) |

## Contraintes
- **Sécurité** : données personnelles et de santé — aucun endpoint accessible sans
  authentification. Un seul utilisateur autorisé (moi).
- **Discrétion** : le dépôt sera public. Le projet se présente comme un journal
  personnel générique ; la catégorie `drinks` est un cas d'usage parmi d'autres.
  Aucune donnée réelle dans le dépôt (ni seed, ni exemples tirés de mes données).
- **Coût visé : zéro.** Rester dans les volets gratuits Azure : pas d'Azure Container
  Registry, logs sobres, Azure SQL en « pause automatique » si retenu, alerte de budget.
- **Risque principal à lever tôt** : la compatibilité du flux OAuth Entra (via FastMCP)
  avec les connecteurs personnalisés claude.ai.
- Développement local possible sans Azure (base locale ou émulateur, MCP Inspector).

## Critères de réussite
- Depuis l'app Claude sur iPhone, « ajoute 2 bières » crée bien l'entrée dans `drinks`.
- « Combien de verres cette semaine ? » renvoie le bon total.
- Ajouter une deuxième catégorie fictive (dans les tests) ne demande aucun changement aux
  outils MCP ni à la catégorie `drinks`.
- Infra entièrement recréable avec `terraform apply` ; déploiement reproductible.
- Tests automatisés sur la logique métier (calcul des verres standard, stats).
- README de qualité portfolio.

## Hors portée (pour l'instant)
- Migration de l'historique Todoist (projet ultérieur).
- Intégration au dashboard santé existant (seule l'API REST est prévue).
- Autres catégories réelles (poids, etc.) — l'architecture doit seulement les permettre.
- Interface web de saisie.
