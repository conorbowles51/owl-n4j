# One isolated environment per customer. No customer exists yet: every identity here
# is a variable, and nothing defaults to the live project. Defaults for sizes are the
# live box's measured shape (8 Nov 2026): e2-custom-6-32768, 500 GB boot (94 % full),
# 1 TB data disk (73 % used) — the boot default below is larger because the live one
# is nearly full.

variable "customer" {
  description = "Short customer slug: lowercase letters, digits, hyphens (used in the project id and resource names)."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,18}$", var.customer))
    error_message = "3-19 chars, lowercase alphanumeric/hyphen, starting with a letter."
  }
}

variable "billing_account" {
  description = "Billing account id the new project attaches to (XXXXXX-XXXXXX-XXXXXX)."
  type        = string
}

variable "org_id" {
  description = "Organization id the project is created under. Leave empty when using folder_id."
  type        = string
  default     = ""
}

variable "folder_id" {
  description = "Folder id the project is created under. Leave empty when using org_id."
  type        = string
  default     = ""
}

variable "region" {
  description = "Region for the customer's resources."
  type        = string
  default     = "us-east1"
}

variable "zone" {
  description = "Zone for the VM (must sit in var.region)."
  type        = string
  default     = "us-east1-c"
}

variable "machine_type" {
  description = "VM shape. Default is the live box's measured shape."
  type        = string
  default     = "e2-custom-6-32768"
}

variable "boot_disk_gb" {
  description = "Boot disk size. The live box's 500 GB is 94 % full, so the default is roomier."
  type        = number
  default     = 650
}

variable "data_disk_gb" {
  description = "Evidence/data disk size. Live box: 1 TB at 73 %."
  type        = number
  default     = 1024
}

variable "alert_email" {
  description = "Address that receives monitoring alerts and the budget emails."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Budget amount (USD/month). Default is an estimate, not measured: VM ~USD 170 + disks ~USD 150 + egress/ops margin."
  type        = number
  default     = 400
}

variable "ssh_source_ranges" {
  description = "CIDRs allowed to reach SSH. Default is Google's IAP range only (no open SSH)."
  type        = list(string)
  default     = ["35.235.240.0/20"]
}

variable "inventory_dir" {
  description = "Directory the instance-inventory entry is written to on apply."
  type        = string
  default     = "./inventory"
}

# The secret names the app needs at runtime (deploy/README.md, .env.example). The
# values are NEVER in Terraform: empty secrets are created and filled on the box
# by deploy/rotate-secrets.sh / by hand.
variable "secret_names" {
  description = "Secret Manager secrets created empty for the customer environment."
  type        = list(string)
  default = [
    "auth-secret-key",
    "ai-credential-encryption-key",
    "postgres-password",
    "neo4j-password",
  ]
}
