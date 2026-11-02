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
