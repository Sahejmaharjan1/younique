variable "project_id" { type = string }
variable "notification_channel" { type = string }

resource "google_monitoring_uptime_check_config" "api" {
  project      = var.project_id
  display_name = "api-healthz"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path = "/healthz"
    port = 443
  }

  monitored_resource {
    type = "uptime_url"
    labels = { host = "api.younique.dev" }
  }
}

output "uptime_check" { value = google_monitoring_uptime_check_config.api.id }
