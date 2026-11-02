# Bootstrap: the resource group and the storage account that holds the remote
# Terraform state of infra/.
#
# The first apply runs with a local state, since the storage account does not exist
# yet (comment out the backend block). The state is then moved into that account
# with `terraform init -migrate-state`.

terraform {
  required_version = ">= 1.9"

  backend "azurerm" {
    resource_group_name  = "rg-lifelog"
    storage_account_name = "stlifelogtfjkgd8v"
    container_name       = "tfstate"
    key                  = "bootstrap.tfstate"
    use_azuread_auth     = true
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.11"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  # Data-plane calls (blob containers) use Entra ID: storage keys stay disabled.
  storage_use_azuread = true
  # Resource providers are registered explicitly below.
  resource_provider_registrations = "none"
}

variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "location" {
  description = "Azure region (D28)."
  type        = string
  default     = "canadacentral"
}

data "azurerm_client_config" "current" {}

# Services used by the project, not registered by default on a new subscription.
resource "azurerm_resource_provider_registration" "this" {
  for_each = toset(["Microsoft.App", "Microsoft.Storage"])
  name     = each.key
}

resource "azurerm_resource_group" "lifelog" {
  name     = "rg-lifelog"
  location = var.location
}

# Storage account names are global: a random suffix avoids collisions.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_storage_account" "tfstate" {
  name                            = "stlifelogtf${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.lifelog.name
  location                        = azurerm_resource_group.lifelog.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  # The Azure portal browses the data with the signed-in identity, not a key.
  default_to_oauth_authentication = true

  blob_properties {
    # Previous versions of the state can be restored after a bad apply.
    versioning_enabled = true
  }

  depends_on = [azurerm_resource_provider_registration.this]
}

# Without storage keys, the person running Terraform needs data-plane access.
resource "azurerm_role_assignment" "tfstate_blob" {
  scope                = azurerm_storage_account.tfstate.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}

output "resource_group_name" {
  value = azurerm_resource_group.lifelog.name
}

output "tfstate_storage_account_name" {
  value = azurerm_storage_account.tfstate.name
}
