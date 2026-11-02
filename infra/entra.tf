# Entra app registration used by the OAuth proxy (AzureProvider).
# Single tenant (D13): only accounts of this directory can sign in, then the server
# applies its own allow-list (D32).

resource "random_uuid" "access_scope" {}

resource "azuread_application" "lifelog" {
  display_name     = "lifelog-mcp"
  sign_in_audience = "AzureADMyOrg"

  api {
    # v2 tokens: the issuer expected by FastMCP's Azure provider.
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.access_scope.result
      value                      = "access"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Use lifelog"
      admin_consent_description  = "Read and write the signed-in user's lifelog."
      user_consent_display_name  = "Use lifelog"
      user_consent_description   = "Read and write your lifelog."
    }
  }

  web {
    redirect_uris = ["${local.base_url}/auth/callback"]
  }

  lifecycle {
    # Managed by azuread_application_identifier_uri below (it needs the client ID).
    ignore_changes = [identifier_uris]
  }
}

# api://<client id>: the default identifier URI expected by AzureProvider.
resource "azuread_application_identifier_uri" "lifelog" {
  application_id = azuread_application.lifelog.id
  identifier_uri = "api://${azuread_application.lifelog.client_id}"
}

resource "azuread_service_principal" "lifelog" {
  client_id = azuread_application.lifelog.client_id
  # Only users explicitly assigned below can get a token: a barrier before the
  # server's own allow-list.
  app_role_assignment_required = true
}

resource "azuread_app_role_assignment" "allowed_users" {
  for_each            = toset(var.allowed_oids)
  app_role_id         = "00000000-0000-0000-0000-000000000000" # default access
  principal_object_id = each.key
  resource_object_id  = azuread_service_principal.lifelog.object_id
}

# The client secret is replaced every year; the new value reaches the Container App
# on the next apply.
resource "time_rotating" "client_secret" {
  rotation_days = 365
}

resource "azuread_application_password" "lifelog" {
  application_id = azuread_application.lifelog.id
  display_name   = "lifelog-container-app"
  end_date       = timeadd(time_rotating.client_secret.id, "9480h") # ~13 months
  rotate_when_changed = {
    rotation = time_rotating.client_secret.id
  }
}
