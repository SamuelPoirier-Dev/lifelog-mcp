# --- Deployment from GitHub Actions (D66-D68) -----------------------------------------------
# GitHub Actions signs in with OIDC: no secret is stored in GitHub. Only jobs of the
# "production" environment of the repository get this identity.

resource "azurerm_user_assigned_identity" "github" {
  name                = "id-lifelog-github"
  resource_group_name = data.azurerm_resource_group.lifelog.name
  location            = data.azurerm_resource_group.lifelog.location
}

resource "azurerm_federated_identity_credential" "github_production" {
  name                      = "github-production"
  user_assigned_identity_id = azurerm_user_assigned_identity.github.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${var.github_repository}:environment:production"
}

# Can update the Container App (new image), nothing else.
resource "azurerm_role_assignment" "github_container_app" {
  scope                = azurerm_container_app.lifelog.id
  role_definition_name = "Container Apps Contributor"
  principal_id         = azurerm_user_assigned_identity.github.principal_id
  # Skips the directory lookup, which can fail right after the identity is created.
  principal_type = "ServicePrincipal"
}
