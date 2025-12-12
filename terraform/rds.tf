# Random password for RDS
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# Store DB password in Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  name                    = "chatbot-db-password"
  description             = "RDS PostgreSQL master password"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

# DB Subnet Group (requires at least 2 subnets in different AZs for RDS)
# We'll create a minimal second subnet just for RDS requirements
resource "aws_subnet" "private_rds" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "chatbot-private-rds-subnet"
    Type = "private"
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "chatbot-db-subnet-group"
  subnet_ids = [aws_subnet.private.id, aws_subnet.private_rds.id]

  tags = {
    Name = "chatbot-db-subnet-group"
  }
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  identifier     = "chatbot-postgres"
  engine         = "postgres"
  engine_version = "17.7" # Latest stable PostgreSQL version

  # Instance configuration (cheapest option)
  instance_class        = var.db_instance_class # db.t4g.micro
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 100 # Auto-scaling up to 100GB
  storage_type          = "gp3" # Latest generation SSD
  storage_encrypted     = true

  # Database configuration
  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result
  port     = 5432

  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # Backup configuration
  backup_retention_period = var.db_backup_retention_period
  backup_window           = "03:00-04:00" # UTC
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # High availability (disabled for cost savings - enable for production)
  multi_az = false

  # Deletion protection
  deletion_protection       = false # Set to true for production
  skip_final_snapshot       = true  # Set to false for production
  final_snapshot_identifier = "chatbot-postgres-final-snapshot"

  # Performance insights (disabled for cost savings)
  enabled_cloudwatch_logs_exports = ["postgresql"]
  monitoring_interval             = 0 # Disable enhanced monitoring

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  tags = {
    Name = "chatbot-postgres"
  }
}
