# S3 Bucket for Resource Storage
# This bucket stores uploaded files (images, PDFs, etc.) for the chatbot application

resource "aws_s3_bucket" "resources" {
  bucket = "chatbot-resources-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "chatbot-resources"
    Environment = var.environment
  }
}

# Random suffix to ensure bucket name uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Block public access - resources are served through the backend API
resource "aws_s3_bucket_public_access_block" "resources" {
  bucket = aws_s3_bucket.resources.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for data protection
resource "aws_s3_bucket_versioning" "resources" {
  bucket = aws_s3_bucket.resources.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "resources" {
  bucket = aws_s3_bucket.resources.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lifecycle rules for cost optimization
resource "aws_s3_bucket_lifecycle_configuration" "resources" {
  bucket = aws_s3_bucket.resources.id

  rule {
    id     = "delete-old-versions"
    status = "Enabled"

    filter {} # Apply to all objects

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {} # Apply to all objects

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

# CORS configuration for frontend access (if needed for direct uploads)
resource "aws_s3_bucket_cors_configuration" "resources" {
  bucket = aws_s3_bucket.resources.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = [
      "https://${var.app_subdomain}.${var.domain_name}",
      "http://localhost:3000",  # For local development
      "http://localhost:5173"   # For Vite dev server
    ]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# IAM Policy for S3 access from ECS tasks
resource "aws_iam_role_policy" "ecs_s3_access" {
  name = "ecs-s3-access-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.resources.arn,
          "${aws_s3_bucket.resources.arn}/*"
        ]
      }
    ]
  })
}
