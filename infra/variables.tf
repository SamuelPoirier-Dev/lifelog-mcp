variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "image" {
  description = "Container image of the first creation; deployments then change it (D66)."
  type        = string
}

variable "allowed_oids" {
  description = "Entra object IDs allowed to use the server (D13, D32)."
  type        = list(string)
}

variable "budget_email" {
  description = "Address that receives the budget alerts (D29)."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget of the subscription, in its billing currency (D29)."
  type        = number
  default     = 5
}

variable "budget_start_date" {
  description = "First day of the first budget month (RFC 3339)."
  type        = string
  default     = "2026-10-01T00:00:00Z"
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name (D67)."
  type        = string
  default     = "SamuelPoirier-Dev/lifelog-mcp"
}
