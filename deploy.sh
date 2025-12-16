#!/bin/bash
set -e

echo "=== Deploying Chatbot Application to AWS ==="
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Please install it first."
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not found. Please install it first."
    exit 1
fi

# Set AWS region
AWS_REGION=${AWS_REGION:-eu-central-1}
export AWS_REGION

echo "Using AWS Region: $AWS_REGION"
echo ""

# Build and push backend
echo "=== Building and pushing backend image ==="
cd backend
chmod +x build-and-push.sh
./build-and-push.sh
cd ..
echo ""

# Build and push frontend
echo "=== Building and pushing frontend image ==="
cd frontend
chmod +x build-and-push.sh
./build-and-push.sh
cd ..
echo ""

# Deploy backend
echo "=== Deploying backend to ECS ==="
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-backend \
  --force-new-deployment \
  --region $AWS_REGION \
  --no-cli-pager

echo "✓ Backend deployment initiated"
echo ""

# Deploy frontend
echo "=== Deploying frontend to ECS ==="
aws ecs update-service \
  --cluster chatbot-cluster \
  --service chatbot-frontend \
  --force-new-deployment \
  --region $AWS_REGION \
  --no-cli-pager

echo "✓ Frontend deployment initiated"
echo ""

echo "=== Deployment Summary ==="
echo "✓ Backend image built and pushed to ECR"
echo "✓ Frontend image built and pushed to ECR"
echo "✓ Backend service deployment initiated"
echo "✓ Frontend service deployment initiated"
echo ""
echo "Monitor deployment status with:"
echo "  ./check-deployment.sh"
echo ""
echo "Or manually:"
echo "  aws ecs describe-services --cluster chatbot-cluster --services chatbot-backend chatbot-frontend --region $AWS_REGION"
echo ""
echo "View logs:"
echo "  aws logs tail /ecs/chatbot-backend --follow --region $AWS_REGION"
echo "  aws logs tail /ecs/chatbot-frontend --follow --region $AWS_REGION"
