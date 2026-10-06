terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "network" { type = string }
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "web_image" { type = string }

module "kms" {
  source     = "../../modules/kms_keyring"
  project_id = var.project_id
  location   = var.region
}

module "sql" {
  source     = "../../modules/cloud_sql"
  project_id = var.project_id
  region     = var.region
  name       = "younique-staging"
  tier       = "db-custom-2-7680"
  network    = var.network
}

module "api" {
  source        = "../../modules/cloud_run_service"
  name          = "api"
  project_id    = var.project_id
  region        = var.region
  image         = var.api_image
  max_instances = 30
}
