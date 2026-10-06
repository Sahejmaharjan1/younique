variable "name" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "image" { type = string }
variable "max_instances" {
  type        = number
  description = "Required. There is no default, so a service cannot scale without an explicit cap."
}
variable "env" {
  type    = map(string)
  default = {}
}

resource "google_cloud_run_v2_service" "this" {
  name     = var.name
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    scaling {
      max_instance_count = var.max_instances
    }
    containers {
      image = var.image
      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}

output "uri" { value = google_cloud_run_v2_service.this.uri }
