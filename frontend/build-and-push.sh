#!/bin/bash
set -e

echo "Fetching configuration from AWS Secrets Manager..."

# Get secrets using AWS CLI's native JSON parsing
PUBLIC_API_URL=$(aws secretsmanager get-secret-value \
  --secret-id chatbot-app-secrets \
  --query 'SecretString' \
  --output text | python -c "import sys, json; print(json.load(sys.stdin)['public_api_url'])")

PUBLIC_LINKEDIN_CLIENT_ID=$(aws secretsmanager get-secret-value \
  --secret-id chatbot-app-secrets \
  --query 'SecretString' \
  --output text | python -c "import sys, json; print(json.load(sys.stdin)['linkedin_client_id'])")

PUBLIC_LINKEDIN_REDIRECT_URI=$(aws secretsmanager get-secret-value \
  --secret-id chatbot-app-secrets \
  --query 'SecretString' \
  --output text | python -c "import sys, json; print(json.load(sys.stdin)['public_linkedin_redirect_uri'])")

# Get ECR repository
ECR_FRONTEND=$(aws ecr describe-repositories \
  --repository-names chatbot-frontend \
  --query 'repositories[0].repositoryUri' \
  --output text)

AWS_REGION=${AWS_REGION:-eu-central-1}

echo "Building frontend with:"
echo "  PUBLIC_API_URL: $PUBLIC_API_URL"
echo "  PUBLIC_LINKEDIN_REDIRECT_URI: $PUBLIC_LINKEDIN_REDIRECT_URI"
echo "  PUBLIC_LINKEDIN_CLIENT_ID: $PUBLIC_LINKEDIN_CLIENT_ID"

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin ${ECR_FRONTEND%/*}

# Build with build arguments
docker build --platform linux/amd64 \
  --build-arg PUBLIC_API_URL="$PUBLIC_API_URL" \
  --build-arg PUBLIC_LINKEDIN_CLIENT_ID="$PUBLIC_LINKEDIN_CLIENT_ID" \
  --build-arg PUBLIC_LINKEDIN_REDIRECT_URI="$PUBLIC_LINKEDIN_REDIRECT_URI" \
  -t chatbot-frontend .

# Tag and push
docker tag chatbot-frontend:latest $ECR_FRONTEND:latest
docker push $ECR_FRONTEND:latest

echo "✓ Frontend image built and pushed successfully"
echo ""
echo "To deploy, run:"
echo "  aws ecs update-service --cluster chatbot-cluster --service chatbot-frontend --force-new-deployment"
