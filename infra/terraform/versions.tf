terraform {
  required_version = ">= 1.5"

  # Configure your Terraform state backend. Example for Azure:
  # backend "azurerm" {
  #   resource_group_name  = "your-resource-group"
  #   storage_account_name = "yourstateaccount"
  #   container_name       = "tfstate"
  #   key                  = "infrastructure/terraform.tfstate"
  # }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.90"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
