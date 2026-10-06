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
  name       = "younique-dev"
  tier       = "db-custom-1-3840"
  network    = var.network
}

module "uploads" {
  source     = "../../modules/gcs_bucket"
  name       = "${var.project_id}-uploads"
  project_id = var.project_id
  location   = var.region
}

module "artifacts" {
  source     = "../../modules/gcs_bucket"
  name       = "${var.project_id}-artifacts"
  project_id = var.project_id
  location   = var.region
  kms_key    = module.kms.kek_id
}

module "tasks_dlq" {
  source     = "../../modules/pubsub_topic"
  name       = "tasks-dlq"
  project_id = var.project_id
}

module "agent_runs" {
  source     = "../../modules/task_queue"
  name       = "agent-runs"
  project_id = var.project_id
  region     = var.region
  dlq_topic  = module.tasks_dlq.dlq
}

module "api" {
  source        = "../../modules/cloud_run_service"
  name          = "api"
  project_id    = var.project_id
  region        = var.region
  image         = var.api_image
  max_instances = 20
}

module "worker" {
  source        = "../../modules/cloud_run_service"
  name          = "worker"
  project_id    = var.project_id
  region        = var.region
  image         = var.worker_image
  max_instances = 50
}

module "web" {
  source        = "../../modules/cloud_run_service"
  name          = "web"
  project_id    = var.project_id
  region        = var.region
  image         = var.web_image
  max_instances = 10
}

module "edge" {
  source     = "../../modules/alb"
  project_id = var.project_id
  name       = "younique-dev"
}

module "monitoring" {
  source               = "../../modules/monitoring"
  project_id           = var.project_id
  notification_channel = ""
}
