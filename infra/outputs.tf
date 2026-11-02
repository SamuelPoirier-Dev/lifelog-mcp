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
