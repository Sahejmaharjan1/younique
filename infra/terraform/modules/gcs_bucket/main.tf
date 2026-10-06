variable "name" { type = string }
variable "project_id" { type = string }
variable "location" { type = string }
variable "kms_key" {
  type    = string
  default = ""
}

resource "google_storage_bucket" "this" {
  name                        = var.name
  project                     = var.project_id
  location                    = var.location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning { enabled = true }

  dynamic "encryption" {
    for_each = var.kms_key == "" ? [] : [var.kms_key]
    content { default_kms_key_name = encryption.value }
  }

  lifecycle_rule {
    condition { age = 30 }
    action { type = "AbortIncompleteMultipartUpload" }
  }
}

output "name" { value = google_storage_bucket.this.name }
