variable "name" { type = string }
variable "project_id" { type = string }

resource "google_pubsub_topic" "dlq" {
  name    = "${var.name}-dlq"
  project = var.project_id
}

resource "google_pubsub_topic" "this" {
  name    = var.name
  project = var.project_id
}

resource "google_pubsub_subscription" "this" {
  name    = "${var.name}-sub"
  project = var.project_id
  topic   = google_pubsub_topic.this.id

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
}

output "topic" { value = google_pubsub_topic.this.id }
output "dlq" { value = google_pubsub_topic.dlq.id }
