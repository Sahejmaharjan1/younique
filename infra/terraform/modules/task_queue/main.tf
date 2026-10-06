variable "name" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "dlq_topic" { type = string }

resource "google_cloud_tasks_queue" "this" {
  name     = var.name
  project  = var.project_id
  location = var.region

  stackdriver_logging_config { sampling_ratio = 1 }

  retry_config {
    max_attempts = 8
  }
}

output "id" { value = google_cloud_tasks_queue.this.id }
output "dlq_topic" { value = var.dlq_topic }
