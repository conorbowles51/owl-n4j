output "project_id" {
  value       = google_project.customer.project_id
  description = "The customer's isolated project."
}

output "app_public_ip" {
  value       = google_compute_instance.app.network_interface[0].access_config[0].nat_ip
  description = "Public address the customer's app serves on."
}

output "backups_bucket" {
  value       = google_storage_bucket.backups.name
  description = "Versioned off-box backup bucket."
}

output "secret_ids" {
  value       = [for s in google_secret_manager_secret.secrets : s.secret_id]
  description = "Secret Manager secrets created empty; fill on the box, never in Terraform."
}

output "inventory_file" {
  value       = local_file.inventory.filename
  description = "This customer's instance-inventory entry (deploy/ci/inventory-check.sh reads it)."
}
