variable "project_id" { type = string }
variable "location" { type = string }

resource "google_kms_key_ring" "this" {
  name     = "younique"
  project  = var.project_id
  location = var.location
}

resource "google_kms_crypto_key" "kek" {
  name     = "app-envelope"
  key_ring = google_kms_key_ring.this.id

  rotation_period = "7776000s"

  lifecycle { prevent_destroy = true }
}

output "kek_id" { value = google_kms_crypto_key.kek.id }
