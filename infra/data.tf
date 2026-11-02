# --- Entries storage: Azure Table Storage (D56, D57, D58) ---------------------------------

# Separate from the OAuth state: the data is precious, the OAuth state is disposable.
resource "azurerm_storage_account" "data" {
  name                            = "stlifelogdata${random_string.suffix.result}"
  resource_group_name             = data.azurerm_resource_group.lifelog.name
  location                        = data.azurerm_resource_group.lifelog.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  # Entra ID only: no storage keys.
  shared_access_key_enabled = false
  # The Azure portal browses the data with the signed-in identity, not a key.
  default_to_oauth_authentication = true
}

resource "azurerm_storage_table" "entries" {
  name               = "entries"
  storage_account_id = azurerm_storage_account.data.id
}

# Azure refuses to delete the account (and its tables) until this lock is removed.
resource "azurerm_management_lock" "data" {
  name       = "protect-lifelog-data"
  scope      = azurerm_storage_account.data.id
  lock_level = "CanNotDelete"
  notes      = "Lifelog entries: remove this lock on purpose before deleting the account."
}

# Table data access: the app's managed identity, and the allowed users for the Azure
# portal and the on-demand tests (D52, D53).
locals {
  data_principals = merge(
    { app = azurerm_container_app.lifelog.identity[0].principal_id },
    { for oid in var.allowed_oids : oid => oid },
  )
}

resource "azurerm_role_assignment" "data_tables" {
  for_each             = local.data_principals
  scope                = azurerm_storage_account.data.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = each.value
}
