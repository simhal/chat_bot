variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "domain_name" {
  description = "Your domain name (must already exist in Route53)"
  type        = string
  # Example: "example.com"
}

variable "app_subdomain" {
  description = "Subdomain for the application"
  type        = string
  default     = "app"
  # Will create: app.example.com
}

# Database Configuration
variable "db_name" {
  description = "Database name"
  type        = string
  default     = "chatbot"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "chatbot_admin"
}

# Application Secrets (set via environment variables or terraform.tfvars)
variable "linkedin_client_id" {
  description = "LinkedIn OAuth Client ID"
  type        = string
  sensitive   = true
}

variable "linkedin_client_secret" {
  description = "LinkedIn OAuth Client Secret"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "JWT secret key for token signing"
  type        = string
  sensitive   = true
}

# ECS Configuration
variable "backend_cpu" {
  description = "CPU units for backend container (1024 = 1 vCPU)"
  type        = number
  default     = 512 # 0.5 vCPU
}

variable "backend_memory" {
  description = "Memory for backend container (MB)"
  type        = number
  default     = 1024 # 1 GB
}

variable "frontend_cpu" {
  description = "CPU units for frontend container"
  type        = number
  default     = 256 # 0.25 vCPU
}

variable "frontend_memory" {
  description = "Memory for frontend container (MB)"
  type        = number
  default     = 512 # 0.5 GB
}

variable "backend_desired_count" {
  description = "Desired number of backend tasks"
  type        = number
  default     = 1
}

variable "frontend_desired_count" {
  description = "Desired number of frontend tasks"
  type        = number
  default     = 1
}

# RDS Configuration
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro" # Cheapest option with 2 vCPUs, 1GB RAM
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS (GB)"
  type        = number
  default     = 20 # Minimum for gp3
}

variable "db_backup_retention_period" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

# ElastiCache Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t4g.micro" # Cheapest option with 0.5GB RAM
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes"
  type        = number
  default     = 1
}

# Deployment Configuration
variable "image_tag" {
  description = "Docker image tag to deploy (e.g., 0.2, latest)"
  type        = string
  default     = "latest"
}
