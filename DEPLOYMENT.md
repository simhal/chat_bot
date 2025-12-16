# AWS Deployment Guide

This guide covers deploying the chatbot application to AWS with the new PDF download feature.

## Prerequisites

1. AWS CLI installed and configured
2. Docker installed
3. Access to the AWS account with appropriate permissions
4. Terraform installed (if infrastructure changes are needed)

## Architecture Overview

The application uses:
- **ECS (Elastic Container Service)**: Runs Docker containers
- **ECR (Elastic Container Registry)**: Stores Docker images
- **RDS PostgreSQL**: Database
- **ElastiCache Redis**: Caching layer
- **ALB (Application Load Balancer)**: Routes traffic
- **Secrets Manager**: Stores sensitive configuration
- **Route53**: DNS management (if configured)

## Changes in This Release

### New Features
- PDF download functionality for articles
- New Python dependencies: `reportlab>=4.0.0`, `markdown2>=2.4.0`

### Database Changes
- **No database schema changes** - No migration needed for this release

## Deployment Steps

### Step 1: Update Dependencies (Local Testing)

First, test locally to ensure everything works:

```bash
# Backend
cd backend
uv sync

# Start local services
cd ..
docker-compose up postgres redis -d

# Test backend
cd backend
uv run uvicorn main:app --reload

# Test frontend
cd ../frontend
npm install
npm run dev
```

### Step 2: Build and Push Backend Image

```bash
cd backend
chmod +x build-and-push.sh
./build-and-push.sh
```

This script will:
1. Login to AWS ECR
2. Build the Docker image with new dependencies
3. Push to ECR repository

**Note:** The backend `Dockerfile` already includes the `uv sync` command which will install the new dependencies (`reportlab` and `markdown2`) automatically.

### Step 3: Build and Push Frontend Image

```bash
cd ../frontend
chmod +x build-and-push.sh
./build-and-push.sh
```

This script will:
1. Fetch configuration from AWS Secrets Manager
2. Login to AWS ECR
3. Build the frontend with environment variables
4. Push to ECR repository

### Step 4: Deploy Backend Service

Deploy the updated backend:

```bash
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-backend \
  --force-new-deployment \
  --region eu-central-1
```

**Important:** The backend entrypoint script (`entrypoint.sh`) automatically:
1. Runs database migrations: `uv run alembic upgrade head`
2. Seeds initial data: `uv run python seed_db.py`
3. Starts the application: `uv run uvicorn main:app --host 0.0.0.0 --port 8000`

Since there are no new migrations for this release, the migration step will complete instantly.

### Step 5: Deploy Frontend Service

```bash
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-frontend \
  --force-new-deployment \
  --region eu-central-1
```

### Step 6: Monitor Deployment

Check the deployment status:

```bash
# Watch backend deployment
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-backend \
  --region eu-central-1 \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Deployments:deployments[*].{Status:rolloutState,Running:runningCount}}'

# Watch frontend deployment
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-frontend \
  --region eu-central-1 \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Deployments:deployments[*].{Status:rolloutState,Running:runningCount}}'
```

### Step 7: Check Logs

If there are any issues, check the logs:

```bash
# Get backend task ARN
BACKEND_TASK=$(aws ecs list-tasks \
  --cluster chatbot-cluster \
  --service-name chatbot-backend \
  --region eu-central-1 \
  --query 'taskArns[0]' \
  --output text)

# View backend logs
aws ecs execute-command \
  --cluster chatbot-cluster \
  --task $BACKEND_TASK \
  --container chatbot-backend \
  --command "/bin/sh" \
  --interactive \
  --region eu-central-1

# Or use CloudWatch Logs
aws logs tail /ecs/chatbot-backend --follow --region eu-central-1
aws logs tail /ecs/chatbot-frontend --follow --region eu-central-1
```

## Rollback Procedure

If the deployment fails, rollback to the previous version:

```bash
# Rollback backend
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-backend \
  --task-definition chatbot-backend:<previous-revision> \
  --force-new-deployment \
  --region eu-central-1

# Rollback frontend
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-frontend \
  --task-definition chatbot-frontend:<previous-revision> \
  --force-new-deployment \
  --region eu-central-1
```

To find previous revisions:

```bash
aws ecs list-task-definitions \
  --family-prefix chatbot-backend \
  --region eu-central-1 \
  --sort DESC
```

## Database Migrations (General Guide)

Although not needed for this release, here's how to handle migrations:

### Creating a New Migration

```bash
cd backend
uv run alembic revision -m "description_of_changes"
```

Edit the generated file in `backend/alembic/versions/` to define upgrade and downgrade operations.

### Running Migrations Manually

Migrations run automatically during deployment via `entrypoint.sh`, but you can run them manually:

```bash
# Connect to ECS task
aws ecs execute-command \
  --cluster chatbot-cluster \
  --task <task-arn> \
  --container chatbot-backend \
  --command "/bin/sh" \
  --interactive \
  --region eu-central-1

# Inside the container
uv run alembic upgrade head
```

### Checking Migration Status

```bash
# Show current revision
uv run alembic current

# Show migration history
uv run alembic history

# Show pending migrations
uv run alembic upgrade head --sql
```

## Testing the Deployment

After deployment, test the new PDF feature:

1. Login to the application
2. Navigate to any content tab (Macro, Equity, Fixed Income, ESG)
3. Click on an article
4. Click the "Download PDF" button
5. Verify the PDF downloads and contains the article content

## Troubleshooting

### PDF Generation Fails

Check if `reportlab` and `markdown2` are installed:

```bash
# Connect to backend container
aws ecs execute-command \
  --cluster chatbot-cluster \
  --task <task-arn> \
  --container chatbot-backend \
  --command "/bin/sh" \
  --interactive

# Inside container
uv pip list | grep reportlab
uv pip list | grep markdown2
```

### Container Fails to Start

Check CloudWatch logs for errors:

```bash
aws logs tail /ecs/chatbot-backend --follow
```

Common issues:
- Database connection failures (check RDS security group)
- Missing environment variables (check Secrets Manager)
- Port conflicts

### Database Connection Issues

Verify database connectivity:

```bash
# Get RDS endpoint
aws rds describe-db-instances \
  --db-instance-identifier chatbot-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text

# Check security groups allow ECS tasks to connect
```

## Complete Deployment Script

For convenience, create a full deployment script:

```bash
#!/bin/bash
set -e

echo "=== Deploying Chatbot Application to AWS ==="

# Build and push backend
echo "Building and pushing backend..."
cd backend
./build-and-push.sh

# Build and push frontend
echo "Building and pushing frontend..."
cd ../frontend
./build-and-push.sh

# Deploy backend
echo "Deploying backend to ECS..."
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-backend \
  --force-new-deployment \
  --region eu-central-1

# Deploy frontend
echo "Deploying frontend to ECS..."
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-frontend \
  --force-new-deployment \
  --region eu-central-1

echo "✓ Deployment initiated successfully"
echo ""
echo "Monitor deployment with:"
echo "  aws ecs describe-services --cluster chatbot-cluster --services chatbot-backend chatbot-frontend --region eu-central-1"
```

Save this as `deploy.sh` in the root directory and make it executable:

```bash
chmod +x deploy.sh
./deploy.sh
```

## Environment Variables

Ensure these are set in AWS Secrets Manager (secret name: `chatbot-app-secrets`):

### Backend
- `linkedin_client_id`
- `linkedin_client_secret`
- `linkedin_redirect_uri`
- `jwt_secret_key`
- `openai_api_key`
- `openai_model`
- `database_url` (RDS connection string)
- `redis_url` (ElastiCache connection string)
- `cors_origins`

### Frontend
- `public_api_url`
- `public_linkedin_client_id`
- `public_linkedin_redirect_uri`

## Post-Deployment Checklist

- [ ] Backend service is running (desired count = running count)
- [ ] Frontend service is running (desired count = running count)
- [ ] Health checks are passing
- [ ] Application loads in browser
- [ ] Users can login
- [ ] Articles load in content tabs
- [ ] PDF download button appears on article detail pages
- [ ] PDF downloads successfully
- [ ] PDF contains correct article content and formatting
- [ ] No errors in CloudWatch logs

## Support

If you encounter issues:
1. Check CloudWatch logs: `/ecs/chatbot-backend` and `/ecs/chatbot-frontend`
2. Verify ECS task health checks
3. Check RDS and ElastiCache connectivity
4. Review ALB target group health
5. Verify Secrets Manager values
