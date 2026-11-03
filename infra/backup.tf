# --- Weekly backup of the entries (D58, D72) ----------------------------------------------
# GitHub Actions exports the table to a dated file in a private container of the data
# account (protected by its lock). Its own identity: it reads the entries and writes the
# backups, nothing else; the deployment identity still cannot read the data.

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_id    = azurerm_storage_account.data.id
  container_access_type = "private"
}

resource "azurerm_user_assigned_identity" "backup" {
  name                = "id-lifelog-backup"
  resource_group_name = data.azurerm_resource_group.lifelog.name
  location            = data.azurerm_resource_group.lifelog.location
}

# Only jobs of the "backup" environment of the repository get this identity.
resource "azurerm_federated_identity_credential" "github_backup" {
  name                      = "github-backup"
  user_assigned_identity_id = azurerm_user_assigned_identity.backup.id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:${var.github_repository}:environment:backup"
}

resource "azurerm_role_assignment" "backup_tables" {
  scope                = azurerm_storage_account.data.id
  role_definition_name = "Storage Table Data Reader"
  principal_id         = azurerm_user_assigned_identity.backup.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "backup_blobs" {
  scope                = azurerm_storage_container.backups.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.backup.principal_id
  principal_type       = "ServicePrincipal"
}

# The allowed users download the backups (Azure portal, CLI) to restore them.
resource "azurerm_role_assignment" "backup_readers" {
  for_each             = toset(var.allowed_oids)
  scope                = azurerm_storage_container.backups.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = each.value
}
