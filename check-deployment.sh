#!/bin/bash

# Set AWS region
AWS_REGION=${AWS_REGION:-eu-central-1}

echo "=== Checking Deployment Status ==="
echo ""

# Check backend service
echo "Backend Service:"
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-backend \
  --region $AWS_REGION \
  --query 'services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount,Deployments:deployments[*].{Status:rolloutState,TaskDef:taskDefinition,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount}}' \
  --output table

echo ""
echo "Frontend Service:"
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-frontend \
  --region $AWS_REGION \
  --query 'services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount,Deployments:deployments[*].{Status:rolloutState,TaskDef:taskDefinition,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount}}' \
  --output table

echo ""
echo "Recent Events:"
echo ""
echo "Backend Events:"
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-backend \
  --region $AWS_REGION \
  --query 'services[0].events[0:5].{Time:createdAt,Message:message}' \
  --output table

echo ""
echo "Frontend Events:"
aws ecs describe-services \
  --cluster chatbot-cluster \
  --services chatbot-frontend \
  --region $AWS_REGION \
  --query 'services[0].events[0:5].{Time:createdAt,Message:message}' \
  --output table
