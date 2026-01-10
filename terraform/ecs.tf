# ECR Repositories
resource "aws_ecr_repository" "backend" {
  name                 = "chatbot-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "chatbot-backend"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "chatbot-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "chatbot-frontend"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "chatbot-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # Disable for cost savings
  }

  tags = {
    Name = "chatbot-cluster"
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/chatbot-backend"
  retention_in_days = 7

  tags = {
    Name = "chatbot-backend-logs"
  }
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/chatbot-frontend"
  retention_in_days = 7

  tags = {
    Name = "chatbot-frontend-logs"
  }
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "ecs_task_execution" {
  name = "chatbot-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# IAM Policy for Secrets Manager access
resource "aws_iam_role_policy" "ecs_secrets" {
  name = "ecs-secrets-policy"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.db_password.arn,
          aws_secretsmanager_secret.app_secrets.arn
        ]
      }
    ]
  })
}

# IAM Role for ECS Tasks
resource "aws_iam_role" "ecs_task" {
  name = "chatbot-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for ECS Exec (SSM access)
resource "aws_iam_role_policy" "ecs_exec" {
  name = "ecs-exec-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# Backend Task Definition
resource "aws_ecs_task_definition" "backend" {
  family                   = "chatbot-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "DATABASE_URL"
          value = "postgresql://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.postgres.endpoint}/${var.db_name}"
        },
        {
          name  = "REDIS_URL"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:${aws_elasticache_cluster.redis.cache_nodes[0].port}/0"
        },
        {
          name  = "CORS_ORIGINS"
          value = "https://${var.app_subdomain}.${var.domain_name}"
        },
        {
          name  = "API_BASE_URL"
          value = "https://${var.app_subdomain}.${var.domain_name}"
        },
        {
          name  = "OPENAI_MODEL"
          value = "gpt-4o-mini"
        },
        {
          name  = "S3_BUCKET"
          value = aws_s3_bucket.resources.id
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "CHROMA_HOST"
          value = "chroma.chatbot.local"
        },
        {
          name  = "CHROMA_PORT"
          value = "8000"
        }
      ]

      secrets = [
        {
          name      = "LINKEDIN_CLIENT_ID"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:linkedin_client_id::"
        },
        {
          name      = "LINKEDIN_CLIENT_SECRET"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:linkedin_client_secret::"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:openai_api_key::"
        },
        {
          name      = "JWT_SECRET_KEY"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:jwt_secret_key::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 5
        startPeriod = 180
      }
    }
  ])
}

# Frontend Task Definition
resource "aws_ecs_task_definition" "frontend" {
  family                   = "chatbot-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = "${aws_ecr_repository.frontend.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "PUBLIC_API_URL"
          value = "https://${var.app_subdomain}.${var.domain_name}"
        },
        {
          name  = "PUBLIC_LINKEDIN_REDIRECT_URI"
          value = "https://${var.app_subdomain}.${var.domain_name}/auth/callback"
        }
      ]

      secrets = [
        {
          name      = "PUBLIC_LINKEDIN_CLIENT_ID"
          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:linkedin_client_id::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# Backend ECS Service
resource "aws_ecs_service" "backend" {
  name                   = "chatbot-backend"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.backend.arn
  desired_count          = var.backend_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  network_configuration {
    subnets          = [aws_subnet.private.id]
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.https,
    aws_ecs_service.chroma
  ]

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# Frontend ECS Service
resource "aws_ecs_service" "frontend" {
  name                   = "chatbot-frontend"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.frontend.arn
  desired_count          = var.frontend_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  network_configuration {
    subnets          = [aws_subnet.private.id]
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [desired_count]
  }
}
