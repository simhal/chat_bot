#!/bin/bash
set -e

# Get ECR repository
ECR_BACKEND=$(aws ecr describe-repositories \
  --repository-names chatbot-backend \
  --query 'repositories[0].repositoryUri' \
  --output text)

AWS_REGION=${AWS_REGION:-eu-central-1}

echo "Building backend..."

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin ${ECR_BACKEND%/*}

# Build for linux/amd64 platform (AWS uses x86_64)
docker build --platform linux/amd64 \
  -t chatbot-backend .

# Tag and push
docker tag chatbot-backend:latest $ECR_BACKEND:latest
docker push $ECR_BACKEND:latest

echo "✓ Backend image built and pushed successfully"
echo ""
echo "To deploy, run:"
echo "  aws ecs update-service --cluster chatbot-cluster --service chatbot-backend --force-new-deployment"
