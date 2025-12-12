# AWS Deployment Guide for Chatbot Application

This guide will help you deploy the chatbot application to AWS using Terraform with ECS Fargate, RDS PostgreSQL, and ElastiCache Redis.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured (`aws configure`)
3. **Terraform** installed (v1.0+)
4. **Docker** installed (for building images)
5. **Domain** already registered in Route53

## Cost Estimate

With the default configuration (single AZ, cheapest options):
- **ECS Fargate**: ~$15-20/month (2 tasks, minimal CPU/RAM, single AZ)
- **RDS db.t4g.micro**: ~$12-15/month (single AZ)
- **ElastiCache cache.t4g.micro**: ~$11-13/month (single AZ)
- **ALB**: ~$16-18/month (2 AZs required by AWS)
- **NAT Gateway**: ~$16-18/month (single gateway)
- **Data Transfer**: ~$3-5/month (reduced with single AZ)
- **Other** (Route53, CloudWatch, Secrets): ~$3-5/month

**Total**: ~$60-75/month

### Cost Optimization Notes

**Already Configured for Maximum Savings:**

1. **Single AZ Deployment**:
   - ECS tasks run in single AZ (no cross-AZ data transfer)
   - Redis in single AZ
   - RDS in single AZ (multi-AZ disabled)
   - Saves ~$5-10/month on data transfer
   - ⚠️ **Tech demo only** - NOT suitable for production

2. **Single NAT Gateway**:
   - Only 1 NAT Gateway instead of 2
   - Saves ~$32/month vs multi-AZ setup
   - ⚠️ Single point of failure for outbound internet

3. **Minimal Resources**:
   - db.t4g.micro (smallest RDS ARM instance)
   - cache.t4g.micro (smallest Redis ARM instance)
   - 0.5 vCPU backend, 0.25 vCPU frontend

**Trade-offs (Acceptable for Tech Demo):**
- ❌ No high availability (single AZ)
- ❌ No automatic failover
- ❌ Single NAT Gateway failure affects all services
- ✅ Saves ~$40-50/month vs production setup

**Further Optimizations** (if needed):
- Use Fargate Spot: Additional 70% savings on compute (~$10-14/month saved)
- Reduce to 1 task each: Saves ~$7-10/month
- Stop services when not testing: $0 for ECS when stopped

## Step 1: Prepare Your Environment

### 1.1 Clone the Repository

```bash
cd chatbot-app/terraform
```

### 1.2 Create terraform.tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
domain_name    = "yourdomain.com"  # Must exist in Route53
app_subdomain  = "app"              # Creates app.yourdomain.com

linkedin_client_id     = "your-linkedin-client-id"
linkedin_client_secret = "your-linkedin-client-secret"
openai_api_key         = "sk-..."
jwt_secret_key         = "random-64-char-string"  # Generate with: openssl rand -base64 64
```

### 1.3 Generate JWT Secret

```bash
openssl rand -base64 64 | tr -d '\n'
```

## Step 2: Build and Push Docker Images

### 2.1 Authenticate Docker to ECR

First, initialize Terraform to create the ECR repositories:

```bash
terraform init
terraform apply -target=aws_ecr_repository.backend -target=aws_ecr_repository.frontend
```

Then authenticate Docker:

```bash
aws ecr get-login-password --region eu-central-1 | docker login --username AWS --password-stdin 091208706603.dkr.ecr.eu-central-1.amazonaws.com
```

### 2.2 Build and Push Backend Image

```bash
cd ../backend

# Build for ARM64 (t4g instances use ARM)
docker buildx build --platform linux/arm64 -t chatbot-backend:latest .

# Tag and push
docker tag chatbot-backend:latest 091208706603.dkr.ecr.eu-central-1.amazonaws.com/chatbot-backend:latest
docker push 091208706603.dkr.ecr.eu-central-1.amazonaws.com/chatbot-backend:latest
```

### 2.3 Build and Push Frontend Image

```bash
cd ../frontend

# Build for ARM64
docker buildx build --platform linux/arm64 -t chatbot-frontend:latest .

# Tag and push
docker tag chatbot-frontend:latest chatbot-frontend:latest 091208706603.dkr.ecr.eu-central-1.amazonaws.com/chatbot-frontend:latest
docker push 091208706603.dkr.ecr.eu-central-1.amazonaws.com/chatbot-frontend:latest
```

**Note**: Replace `<ecr-backend-url>` and `<ecr-frontend-url>` with the outputs from step 2.1.

## Step 3: Deploy Infrastructure

### 3.1 Review the Plan

```bash
terraform plan
```

Review the planned changes carefully.

### 3.2 Apply the Configuration

```bash
terraform apply
```

Type `yes` when prompted.

**Deployment time**: ~15-20 minutes

## Step 4: Run Database Migrations

After deployment, you need to run the database migrations:

### 4.1 Connect to Backend Task

```bash
# Get the task ARN
TASK_ARN=$(aws ecs list-tasks \
  --cluster chatbot-cluster \
  --service-name chatbot-backend \
  --query 'taskArns[0]' \
  --output text)

# Execute migrations
aws ecs execute-command \
  --cluster chatbot-cluster \
  --task $TASK_ARN \
  --container backend \
  --interactive \
  --command "/bin/sh"
```

### 4.2 Run Alembic Migrations

Inside the container:

```bash
uv run alembic upgrade head
exit
```

### 4.3 Initialize Admin User

```bash
# Connect to RDS directly
DB_ENDPOINT=$(terraform output -raw rds_endpoint)
DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id chatbot-db-password \
  --query SecretString \
  --output text)

# Use psql or any PostgreSQL client
psql -h $DB_ENDPOINT -U chatbot_admin -d chatbot

# Inside psql:
INSERT INTO groups (name, description) VALUES ('admin', 'Administrator group');
INSERT INTO groups (name, description) VALUES ('user', 'Default user group');
```

## Step 5: Access Your Application

Your application will be available at: `https://app.yourdomain.com`

The SSL certificate may take a few minutes to validate and propagate.

## Step 6: Update LinkedIn OAuth Settings

Update your LinkedIn application OAuth settings:
- **Redirect URL**: `https://app.yourdomain.com/auth/callback`

## Monitoring and Logs

### View Logs

```bash
# Backend logs
aws logs tail /ecs/chatbot-backend --follow

# Frontend logs
aws logs tail /ecs/chatbot-frontend --follow
```

### ECS Service Status

```bash
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-backend chatbot-frontend
```

### Database Metrics

View in AWS Console: RDS → Databases → chatbot-postgres → Monitoring

## Updating the Application

### Update Backend

```bash
cd backend
docker buildx build --platform linux/arm64 -t chatbot-backend:latest .
docker tag chatbot-backend:latest <ecr-backend-url>:latest
docker push <ecr-backend-url>:latest

# Force new deployment
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-backend \
  --force-new-deployment
```

### Update Frontend

```bash
cd frontend
docker buildx build --platform linux/arm64 -t chatbot-frontend:latest .
docker tag chatbot-frontend:latest <ecr-frontend-url>:latest
docker push <ecr-frontend-url>:latest

# Force new deployment
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-frontend \
  --force-new-deployment
```

## Backup and Restore

### Manual Backup

```bash
aws rds create-db-snapshot \
  --db-instance-identifier chatbot-postgres \
  --db-snapshot-identifier chatbot-manual-backup-$(date +%Y%m%d)
```

### Restore from Snapshot

1. Go to RDS Console
2. Select Snapshots
3. Choose snapshot and click "Restore"
4. Update Terraform state or modify endpoint

## Scaling

### Horizontal Scaling (More Tasks)

Edit `terraform.tfvars`:

```hcl
backend_desired_count  = 2
frontend_desired_count = 2
```

Then apply:

```bash
terraform apply
```

### Vertical Scaling (More Resources)

Edit `terraform.tfvars`:

```hcl
backend_cpu    = 1024  # 1 vCPU
backend_memory = 2048  # 2 GB
```

Then apply:

```bash
terraform apply
```

## Troubleshooting

### Tasks Won't Start

1. Check logs: `aws logs tail /ecs/chatbot-backend --follow`
2. Verify secrets: `aws secretsmanager get-secret-value --secret-id chatbot-app-secrets`
3. Check security groups and network connectivity

### Database Connection Issues

1. Verify RDS is in "available" state
2. Check security group rules
3. Verify database password in Secrets Manager

### SSL Certificate Not Validating

1. Check Route53 has the validation CNAME records
2. Wait up to 30 minutes for DNS propagation
3. Verify domain ownership in Route53

## Security Best Practices

1. **Enable MFA** on your AWS account
2. **Use IAM roles** instead of access keys
3. **Enable CloudTrail** for audit logging
4. **Enable GuardDuty** for threat detection
5. **Regular security updates**: Rebuild and redeploy images monthly
6. **Rotate secrets**: Use AWS Secrets Manager rotation

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning**: This will delete:
- All data in RDS (unless you've disabled `skip_final_snapshot`)
- All Redis cache data
- All logs
- All container images in ECR

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review AWS service health dashboard
3. Consult AWS documentation

## Next Steps

1. **Set up CI/CD**: Use AWS CodePipeline or GitHub Actions
2. **Add monitoring**: CloudWatch dashboards and alarms
3. **Enable auto-scaling**: ECS Service Auto Scaling
4. **Add WAF**: AWS WAF for application protection
5. **Set up backups**: Automated RDS snapshots and point-in-time recovery
