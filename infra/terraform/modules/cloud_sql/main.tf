variable "project_id" { type = string }
variable "region" { type = string }
variable "name" { type = string }
variable "tier" { type = string }
variable "network" { type = string }

resource "google_sql_database_instance" "this" {
  name             = var.name
  project          = var.project_id
  region           = var.region
  database_version = "POSTGRES_16"

  settings {
    tier = var.tier
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
}

resource "google_sql_database" "app" {
  name     = "younique"
  project  = var.project_id
  instance = google_sql_database_instance.this.name
}

output "connection_name" { value = google_sql_database_instance.this.connection_name }
output "private_ip" { value = google_sql_database_instance.this.private_ip_address }
