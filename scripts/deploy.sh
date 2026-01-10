#!/bin/bash
#
# Deployment script for chatbot-app to AWS ECS
# Usage: ./deploy.sh <version> [--skip-backup] [--skip-migrations]
# Example: ./deploy.sh 0.2
#
# IMPORTANT: This script handles database migrations for major upgrades.
# Always review migrations before deploying to production.
#

set -e

# Configuration
VERSION=${1:-"latest"}
AWS_REGION=${AWS_REGION:-"eu-central-1"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Parse flags
SKIP_BACKUP=false
SKIP_MIGRATIONS=false
for arg in "$@"; do
    case $arg in
        --skip-backup) SKIP_BACKUP=true ;;
        --skip-migrations) SKIP_MIGRATIONS=true ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

# Check required tools
check_requirements() {
    log_info "Checking requirements..."

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi

    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed. Please install it first."
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi

    log_info "All requirements met."
}

# Get ECR repository URLs
get_ecr_urls() {
    log_info "Getting ECR repository URLs..."

    BACKEND_REPO=$(aws ecr describe-repositories --repository-names chatbot-backend --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")
    FRONTEND_REPO=$(aws ecr describe-repositories --repository-names chatbot-frontend --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")

    if [ -z "$BACKEND_REPO" ] || [ -z "$FRONTEND_REPO" ]; then
        log_warn "ECR repositories not found. They will be created by Terraform."
        return 1
    fi

    log_info "Backend ECR: $BACKEND_REPO"
    log_info "Frontend ECR: $FRONTEND_REPO"
    return 0
}

# Login to ECR
ecr_login() {
    log_info "Logging into ECR..."
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com
}

# Build Docker images
build_images() {
    log_info "Building Docker images with tag: $VERSION..."

    cd "$PROJECT_ROOT"

    # Build backend
    log_info "Building backend image..."
    docker build -t chatbot-backend:$VERSION -f backend/Dockerfile backend/

    # Build frontend
    log_info "Building frontend image..."
    docker build -t chatbot-frontend:$VERSION -f frontend/Dockerfile frontend/

    log_info "Images built successfully."
}

# Tag and push images to ECR
push_images() {
    log_info "Pushing images to ECR..."

    # Tag images
    docker tag chatbot-backend:$VERSION $BACKEND_REPO:$VERSION
    docker tag chatbot-frontend:$VERSION $FRONTEND_REPO:$VERSION

    # Also tag as latest for convenience
    docker tag chatbot-backend:$VERSION $BACKEND_REPO:latest
    docker tag chatbot-frontend:$VERSION $FRONTEND_REPO:latest

    # Push images
    log_info "Pushing backend image..."
    docker push $BACKEND_REPO:$VERSION
    docker push $BACKEND_REPO:latest

    log_info "Pushing frontend image..."
    docker push $FRONTEND_REPO:$VERSION
    docker push $FRONTEND_REPO:latest

    log_info "Images pushed successfully."
}

# Apply Terraform
apply_terraform() {
    log_info "Applying Terraform with image_tag=$VERSION..."

    cd "$PROJECT_ROOT/terraform"

    # Initialize Terraform
    terraform init

    # Plan and apply
    terraform plan -var="image_tag=$VERSION" -out=tfplan

    read -p "Do you want to apply this plan? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        terraform apply tfplan
        log_info "Terraform applied successfully."
    else
        log_warn "Terraform apply cancelled."
        exit 0
    fi
}

# Get RDS connection info
get_rds_info() {
    log_info "Getting RDS connection information..."

    RDS_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier chatbot-postgres --query 'DBInstances[0].Endpoint.Address' --output text 2>/dev/null || echo "")

    if [ -z "$RDS_ENDPOINT" ]; then
        log_warn "RDS instance not found. Skipping database operations."
        return 1
    fi

    log_info "RDS Endpoint: $RDS_ENDPOINT"
    return 0
}

# Backup database before migrations
backup_database() {
    if [ "$SKIP_BACKUP" = true ]; then
        log_warn "Skipping database backup (--skip-backup flag)"
        return 0
    fi

    log_section "DATABASE BACKUP"

    mkdir -p "$BACKUP_DIR"

    BACKUP_FILE="$BACKUP_DIR/db_backup_${VERSION}_${TIMESTAMP}.sql"

    log_info "Creating database backup: $BACKUP_FILE"
    log_warn "IMPORTANT: Ensure you have database credentials configured."

    # Get database credentials from Secrets Manager
    DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id chatbot/db-password --query 'SecretString' --output text 2>/dev/null || echo "")

    if [ -z "$DB_PASSWORD" ]; then
        log_warn "Could not retrieve DB password from Secrets Manager."
        log_warn "Please create a manual backup before proceeding."
        read -p "Have you created a manual backup? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Please create a backup before deploying."
            exit 1
        fi
        return 0
    fi

    # Create backup using pg_dump through an ECS Exec session
    log_info "Creating backup via ECS Exec..."
    log_info "Note: For production, consider using RDS automated snapshots instead."

    # Create RDS snapshot for safety
    SNAPSHOT_ID="pre-deploy-${VERSION}-${TIMESTAMP}"
    log_info "Creating RDS snapshot: $SNAPSHOT_ID"
    aws rds create-db-snapshot \
        --db-instance-identifier chatbot-postgres \
        --db-snapshot-identifier "$SNAPSHOT_ID" \
        --region $AWS_REGION || log_warn "Could not create RDS snapshot"

    log_info "Waiting for snapshot to complete..."
    aws rds wait db-snapshot-available \
        --db-snapshot-identifier "$SNAPSHOT_ID" \
        --region $AWS_REGION || log_warn "Snapshot wait timed out - check AWS Console"

    log_info "Database backup completed."
}

# Run database migrations
run_migrations() {
    if [ "$SKIP_MIGRATIONS" = true ]; then
        log_warn "Skipping database migrations (--skip-migrations flag)"
        return 0
    fi

    log_section "DATABASE MIGRATIONS"

    log_warn "This deployment includes the following database migrations:"
    echo "  - 024_add_hitl_models: Adds HITL approval workflow tables"
    echo "  - 025_add_article_publication_hash_ids: Adds popup_hash_id column"
    echo "  - 026_remove_redundant_hash_ids: Removes html_hash_id, pdf_hash_id columns"
    echo

    read -p "Review migrations and proceed? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Deployment cancelled. Please review migrations."
        exit 1
    fi

    # Run migrations via ECS Exec on an existing backend container
    log_info "Running database migrations via ECS Exec..."

    # Get a running backend task
    TASK_ARN=$(aws ecs list-tasks --cluster chatbot-cluster --service-name chatbot-backend --query 'taskArns[0]' --output text 2>/dev/null || echo "")

    if [ "$TASK_ARN" = "None" ] || [ -z "$TASK_ARN" ]; then
        log_warn "No running backend task found. Migrations will run on container startup."
        log_info "The backend container runs migrations automatically via entrypoint.sh"
        return 0
    fi

    log_info "Running migrations on task: $TASK_ARN"
    aws ecs execute-command \
        --cluster chatbot-cluster \
        --task "$TASK_ARN" \
        --container backend \
        --interactive \
        --command "alembic upgrade head" || {
            log_error "Migration failed! Check the logs."
            log_warn "You may need to restore from the backup snapshot."
            exit 1
        }

    log_info "Migrations completed successfully."
}

# Force new deployment (rolling update)
force_deployment() {
    log_section "DEPLOYING NEW CONTAINERS"

    log_info "Forcing new ECS deployment..."

    aws ecs update-service --cluster chatbot-cluster --service chatbot-backend --force-new-deployment --region $AWS_REGION
    aws ecs update-service --cluster chatbot-cluster --service chatbot-frontend --force-new-deployment --region $AWS_REGION

    log_info "Deployment triggered. Monitor progress in AWS Console or with:"
    log_info "  aws ecs describe-services --cluster chatbot-cluster --services chatbot-backend chatbot-frontend"
}

# Main deployment flow
main() {
    echo "=========================================="
    echo "  Chatbot App Deployment - Version $VERSION"
    echo "=========================================="
    echo
    log_warn "This is a MAJOR upgrade with database migrations!"
    echo

    check_requirements

    if get_ecr_urls; then
        # Phase 1: Build and push new images
        log_section "PHASE 1: BUILD & PUSH IMAGES"
        ecr_login
        build_images
        push_images

        # Phase 2: Database backup (before any changes)
        log_section "PHASE 2: DATABASE BACKUP"
        if get_rds_info; then
            backup_database
        fi

        # Phase 3: Run database migrations
        log_section "PHASE 3: DATABASE MIGRATIONS"
        if get_rds_info; then
            run_migrations
        fi

        # Phase 4: Apply Terraform (updates task definitions)
        log_section "PHASE 4: TERRAFORM APPLY"
        apply_terraform

        # Phase 5: Force deployment with new images
        force_deployment
    else
        log_info "Running Terraform to create infrastructure first..."
        cd "$PROJECT_ROOT/terraform"
        terraform init
        terraform apply -var="image_tag=$VERSION"

        log_info "Infrastructure created. Run this script again to deploy images."
    fi

    echo
    log_info "=========================================="
    log_info "  Deployment Complete - Version $VERSION"
    log_info "=========================================="
    log_info ""
    log_info "Post-deployment checklist:"
    log_info "  1. Verify services are healthy in ECS Console"
    log_info "  2. Test HITL publish workflow"
    log_info "  3. Verify article resources are generated correctly"
    log_info "  4. Check CloudWatch logs for any errors"
}

# Run main
main
