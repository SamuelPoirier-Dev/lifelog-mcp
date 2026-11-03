output "base_url" {
  description = "Public URL of the server."
  value       = local.base_url
}

output "mcp_url" {
  description = "URL to add as a custom connector on claude.ai."
  value       = "${local.base_url}/mcp"
}

output "entra_client_id" {
  value = azuread_application.lifelog.client_id
}

output "data_storage_account" {
  description = "Storage account of the entries table (also for the on-demand tests, D52)."
  value       = azurerm_storage_account.data.name
}

# Repository variables of GitHub Actions (identifiers, not secrets).
output "github_variables" {
  description = "AZURE_* variables to set on the GitHub repository."
  value = {
    AZURE_CLIENT_ID       = azurerm_user_assigned_identity.github.client_id
    AZURE_TENANT_ID       = data.azurerm_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID = var.subscription_id
  }
}
