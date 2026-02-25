# =============================================================================
# IronLayer Infrastructure Outputs — Azure
# =============================================================================

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------

output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = azurerm_virtual_network.this.id
}

output "apps_subnet_id" {
  description = "ID of the Container Apps subnet"
  value       = azurerm_subnet.apps.id
}

output "database_subnet_id" {
  description = "ID of the database subnet"
  value       = azurerm_subnet.database.id
}

# -----------------------------------------------------------------------------
# Container Apps
# -----------------------------------------------------------------------------

output "container_app_environment_id" {
  description = "ID of the Container App Environment"
  value       = azurerm_container_app_environment.this.id
}

output "api_fqdn" {
  description = "Fully qualified domain name of the API Container App"
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "ai_fqdn" {
  description = "Fully qualified domain name of the AI engine Container App (internal)"
  value       = azurerm_container_app.ai.ingress[0].fqdn
}

output "frontend_fqdn" {
  description = "Fully qualified domain name of the frontend Container App"
  value       = azurerm_container_app.frontend.ingress[0].fqdn
}

output "frontend_url" {
  description = "Public URL for the frontend application"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "api_url" {
  description = "Public URL for the API service"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

output "postgresql_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL Flexible Server"
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "postgresql_server_name" {
  description = "Name of the PostgreSQL Flexible Server"
  value       = azurerm_postgresql_flexible_server.this.name
}

# -----------------------------------------------------------------------------
# Container Registry
# -----------------------------------------------------------------------------

output "acr_login_server" {
  description = "Login server URL for the Azure Container Registry"
  value       = azurerm_container_registry.this.login_server
}

output "acr_name" {
  description = "Name of the Azure Container Registry"
  value       = azurerm_container_registry.this.name
}

# -----------------------------------------------------------------------------
# Key Vault
# -----------------------------------------------------------------------------

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.this.vault_uri
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.this.name
}

# -----------------------------------------------------------------------------
# Identity
# -----------------------------------------------------------------------------

output "managed_identity_client_id" {
  description = "Client ID of the user-assigned managed identity for Container Apps"
  value       = azurerm_user_assigned_identity.apps.client_id
}

# -----------------------------------------------------------------------------
# Observability
# -----------------------------------------------------------------------------

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics Workspace"
  value       = azurerm_log_analytics_workspace.this.id
}

output "log_analytics_workspace_name" {
  description = "Name of the Log Analytics Workspace"
  value       = azurerm_log_analytics_workspace.this.name
}

# -----------------------------------------------------------------------------
# Convenience — CI/CD Integration
# -----------------------------------------------------------------------------

output "deploy_command_api" {
  description = "Azure CLI command to update the API container app"
  value       = "az containerapp update --name ${azurerm_container_app.api.name} --resource-group ${data.azurerm_resource_group.this.name} --image ${azurerm_container_registry.this.login_server}/${var.project_name}-api:TAG"
}

output "deploy_command_ai" {
  description = "Azure CLI command to update the AI engine container app"
  value       = "az containerapp update --name ${azurerm_container_app.ai.name} --resource-group ${data.azurerm_resource_group.this.name} --image ${azurerm_container_registry.this.login_server}/${var.project_name}-ai:TAG"
}

output "deploy_command_frontend" {
  description = "Azure CLI command to update the frontend container app"
  value       = "az containerapp update --name ${azurerm_container_app.frontend.name} --resource-group ${data.azurerm_resource_group.this.name} --image ${azurerm_container_registry.this.login_server}/${var.project_name}-frontend:TAG"
}

output "acr_build_command" {
  description = "Azure CLI command to build and push an image using ACR Tasks"
  value       = "az acr build --registry ${azurerm_container_registry.this.name} --image IMAGE_NAME:TAG ."
}
