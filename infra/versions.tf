terraform {
  required_version = ">= 1.9"

  # Remote state in the storage account created by infra/bootstrap/.
  backend "azurerm" {
    resource_group_name  = "rg-lifelog"
    storage_account_name = "stlifelogtfjkgd8v"
    container_name       = "tfstate"
    key                  = "lifelog.tfstate"
    use_azuread_auth     = true
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.11"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}

provider "azuread" {}
