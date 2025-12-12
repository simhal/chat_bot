# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  name       = "chatbot-redis-subnet-group"
  subnet_ids = [aws_subnet.private.id]

  tags = {
    Name = "chatbot-redis-subnet-group"
  }
}

# ElastiCache Redis Cluster
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "chatbot-redis"
  engine               = "redis"
  engine_version       = "7.1" # Latest Redis version supported
  node_type            = var.redis_node_type # cache.t4g.micro (cheapest)
  num_cache_nodes      = var.redis_num_cache_nodes
  parameter_group_name = "default.redis7"
  port                 = 6379

  # Network configuration
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Backup configuration (optional, adds cost)
  snapshot_retention_limit = 0 # Disable snapshots for cost savings
  # snapshot_window          = "03:00-05:00" # Uncomment if enabling snapshots

  # Maintenance window
  maintenance_window = "sun:05:00-sun:06:00"

  # Encryption at rest (optional, may add cost)
  # at_rest_encryption_enabled = true

  # Encryption in transit
  # transit_encryption_enabled = true

  tags = {
    Name = "chatbot-redis"
  }
}
