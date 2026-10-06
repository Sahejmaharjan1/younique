terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "younique-tf-state"
    prefix = "shared"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { type = string }
variable "region" { type = string }

resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "app"
  format        = "DOCKER"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_storage_bucket" "tf_state" {
  name                        = "younique-tf-state"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning { enabled = true }
}
