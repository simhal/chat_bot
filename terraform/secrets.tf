# Secrets Manager for Application Secrets
resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "chatbot-app-secrets"
  description             = "Application secrets for chatbot"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    linkedin_client_id        = var.linkedin_client_id
    linkedin_client_secret    = var.linkedin_client_secret
    openai_api_key            = var.openai_api_key
    jwt_secret_key            = var.jwt_secret_key
    public_api_url            = "https://${var.app_subdomain}.${var.domain_name}"
    public_linkedin_redirect_uri = "https://${var.app_subdomain}.${var.domain_name}/auth/callback"
  })
}

# Random password generator
resource "random_password" "jwt_secret" {
  count   = var.jwt_secret_key == "" ? 1 : 0
  length  = 64
  special = true
}
