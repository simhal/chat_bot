# ChromaDB Vector Database for ECS
# Provides semantic search capabilities for articles

# CloudWatch Log Group for ChromaDB
resource "aws_cloudwatch_log_group" "chroma" {
  name              = "/ecs/chatbot-chroma"
  retention_in_days = 7

  tags = {
    Name = "chatbot-chroma-logs"
  }
}

# EFS File System for ChromaDB persistent storage
resource "aws_efs_file_system" "chroma" {
  creation_token = "chatbot-chroma-efs"
  encrypted      = true

  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name = "chatbot-chroma-efs"
  }
}

# EFS Mount Target in private subnet
resource "aws_efs_mount_target" "chroma" {
  file_system_id  = aws_efs_file_system.chroma.id
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.efs.id]
}

# Security Group for EFS
resource "aws_security_group" "efs" {
  name        = "chatbot-efs-sg"
  description = "Security group for EFS mount targets"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from ChromaDB"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.chroma.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "chatbot-efs-sg"
  }
}

# Security Group for ChromaDB
resource "aws_security_group" "chroma" {
  name        = "chatbot-chroma-sg"
  description = "Security group for ChromaDB service"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from backend only
  ingress {
    description     = "ChromaDB API from backend"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "chatbot-chroma-sg"
  }
}

# EFS Access Point for ChromaDB
resource "aws_efs_access_point" "chroma" {
  file_system_id = aws_efs_file_system.chroma.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/chroma-data"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }

  tags = {
    Name = "chatbot-chroma-ap"
  }
}

# ChromaDB Task Definition
resource "aws_ecs_task_definition" "chroma" {
  family                   = "chatbot-chroma"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  volume {
    name = "chroma-data"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.chroma.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.chroma.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "chroma"
      image     = "chromadb/chroma:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "IS_PERSISTENT"
          value = "TRUE"
        },
        {
          name  = "ANONYMIZED_TELEMETRY"
          value = "FALSE"
        },
        {
          name  = "CHROMA_SERVER_AUTHN_PROVIDER"
          value = ""
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "chroma-data"
          containerPath = "/data"
          readOnly      = false
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.chroma.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      # Health check disabled - ChromaDB container lacks curl/wget
      # The ALB/service will handle availability checks
      # healthCheck = {
      #   command     = ["CMD-SHELL", "echo healthy"]
      #   interval    = 30
      #   timeout     = 5
      #   retries     = 3
      #   startPeriod = 60
      # }
    }
  ])
}

# ChromaDB ECS Service with Service Discovery
resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = "chatbot.local"
  description = "Private DNS namespace for chatbot services"
  vpc         = aws_vpc.main.id

  tags = {
    Name = "chatbot-dns-namespace"
  }
}

resource "aws_service_discovery_service" "chroma" {
  name = "chroma"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }

  tags = {
    Name = "chatbot-chroma-discovery"
  }
}

resource "aws_ecs_service" "chroma" {
  name                   = "chatbot-chroma"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.chroma.arn
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true
  platform_version       = "1.4.0" # Required for EFS

  network_configuration {
    subnets          = [aws_subnet.private.id]
    security_groups  = [aws_security_group.chroma.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.chroma.arn
  }

  depends_on = [aws_efs_mount_target.chroma]

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# IAM policy for EFS access
resource "aws_iam_role_policy" "ecs_efs_access" {
  name = "ecs-efs-access-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "elasticfilesystem:ClientMount",
          "elasticfilesystem:ClientWrite",
          "elasticfilesystem:ClientRootAccess"
        ]
        Resource = aws_efs_file_system.chroma.arn
        Condition = {
          StringEquals = {
            "elasticfilesystem:AccessPointArn" = aws_efs_access_point.chroma.arn
          }
        }
      }
    ]
  })
}
