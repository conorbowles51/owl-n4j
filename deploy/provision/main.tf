# One isolated customer environment: its own project, network, VM, storage, secrets,
# backups, monitoring and budget. Everything lives inside the new per-customer project;
# nothing references the live project. validate and plan only until Neil says apply.

locals {
  project_id = "loupe-${var.customer}"
  labels = {
    app      = "loupe"
    customer = var.customer
    managed  = "terraform"
  }
}

# --- Isolated project --------------------------------------------------------
resource "google_project" "customer" {
  name            = "Loupe ${var.customer}"
  project_id      = local.project_id
  org_id          = var.org_id != "" ? var.org_id : null
  folder_id       = var.folder_id != "" ? var.folder_id : null
  billing_account = var.billing_account
  labels          = local.labels
}

resource "google_project_service" "services" {
  for_each = toset([
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "storage.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
  project            = google_project.customer.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- Network -----------------------------------------------------------------
resource "google_compute_network" "net" {
  project                 = google_project.customer.project_id
  name                    = "loupe-${var.customer}-net"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.services]
}

resource "google_compute_subnetwork" "subnet" {
  project       = google_project.customer.project_id
  name          = "loupe-${var.customer}-subnet"
  region        = var.region
  network       = google_compute_network.net.id
  ip_cidr_range = "10.10.0.0/24"
}

resource "google_compute_firewall" "allow_web" {
  project       = google_project.customer.project_id
  name          = "loupe-${var.customer}-allow-web"
  network       = google_compute_network.net.name
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["loupe-app"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

resource "google_compute_firewall" "allow_ssh_iap" {
  project       = google_project.customer.project_id
  name          = "loupe-${var.customer}-allow-ssh"
  network       = google_compute_network.net.name
  direction     = "INGRESS"
  source_ranges = var.ssh_source_ranges
  target_tags   = ["loupe-app"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# --- VM and disks (shape measured from the live box) ---------------------------
resource "google_compute_disk" "data" {
  project = google_project.customer.project_id
  name    = "loupe-${var.customer}-data"
  zone    = var.zone
  type    = "pd-balanced"
  size    = var.data_disk_gb
  labels  = local.labels
}

resource "google_compute_instance" "app" {
  project      = google_project.customer.project_id
  name         = "loupe-${var.customer}-app"
  zone         = var.zone
  machine_type = var.machine_type
  tags         = ["loupe-app"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = var.boot_disk_gb
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "owl-data"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {} # ephemeral public IP; the app serves 80/443 directly today
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  depends_on = [google_project_service.services]
}

# --- Storage (off-box backup target) ------------------------------------------
resource "google_storage_bucket" "backups" {
  project                     = google_project.customer.project_id
  name                        = "loupe-${var.customer}-backups"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
  labels     = local.labels
  depends_on = [google_project_service.services]
}

# --- Secrets (created empty; values are set on the box, never in Terraform) ----
resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(var.secret_names)
  project   = google_project.customer.project_id
  secret_id = "loupe-${var.customer}-${each.value}"
  replication {
    auto {}
  }
  labels     = local.labels
  depends_on = [google_project_service.services]
}

# --- Backups: daily snapshots of the data disk ---------------------------------
resource "google_compute_resource_policy" "daily_snapshot" {
  project = google_project.customer.project_id
  name    = "loupe-${var.customer}-daily-snapshot"
  region  = var.region
  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "06:00"
      }
    }
    retention_policy {
      max_retention_days    = 30
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
  depends_on = [google_project_service.services]
}

resource "google_compute_disk_resource_policy_attachment" "data_snapshots" {
  project = google_project.customer.project_id
  name    = google_compute_resource_policy.daily_snapshot.name
  disk    = google_compute_disk.data.name
  zone    = var.zone
}

# --- Monitoring: uptime check on the app + alert to email ----------------------
resource "google_monitoring_notification_channel" "email" {
  project      = google_project.customer.project_id
  display_name = "Loupe ${var.customer} alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.services]
}

resource "google_monitoring_uptime_check_config" "app" {
  project      = google_project.customer.project_id
  display_name = "loupe-${var.customer}-uptime"
  timeout      = "10s"
  period       = "300s"
  http_check {
    path = "/health"
    port = 80
  }
  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = google_project.customer.project_id
      host       = google_compute_instance.app.network_interface[0].access_config[0].nat_ip
    }
  }
}

resource "google_monitoring_alert_policy" "uptime" {
  project      = google_project.customer.project_id
  display_name = "loupe-${var.customer} app unreachable"
  combiner     = "OR"
  conditions {
    display_name = "uptime check failing"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.app.uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}

# --- Budget --------------------------------------------------------------------
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "loupe-${var.customer} monthly"
  budget_filter {
    projects = ["projects/${google_project.customer.number}"]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
}

# --- Instance inventory entry (written on apply; checked by deploy/ci) ----------
resource "local_file" "inventory" {
  filename        = "${var.inventory_dir}/${var.customer}.json"
  file_permission = "0644"
  content = jsonencode({
    customer        = var.customer
    region          = var.region
    version         = "not deployed yet (provisioned by terraform, no release on the VM)"
    health          = "not deployed yet"
    backup_state    = "daily data-disk snapshots (30-day retention) + versioned bucket ${google_storage_bucket.backups.name}"
    last_deployment = "never"
    written         = timestamp()
    written_by      = "deploy/provision (terraform apply)"
  })
}
