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
  name       = "younique-prod"
  tier       = "db-custom-4-15360"
  network    = var.network
}

module "api" {
  source        = "../../modules/cloud_run_service"
  name          = "api"
  project_id    = var.project_id
  region        = var.region
  image         = var.api_image
  max_instances = 100
}

module "worker" {
  source        = "../../modules/cloud_run_service"
  name          = "worker"
  project_id    = var.project_id
  region        = var.region
  image         = var.worker_image
  max_instances = 200
}

module "web" {
  source        = "../../modules/cloud_run_service"
  name          = "web"
  project_id    = var.project_id
  region        = var.region
  image         = var.web_image
  max_instances = 40
}

module "edge" {
  source     = "../../modules/alb"
  project_id = var.project_id
  name       = "younique-prod"
}
