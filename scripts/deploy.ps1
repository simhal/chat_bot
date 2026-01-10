#
# Deployment script for chatbot-app to AWS ECS (PowerShell)
# Usage: .\deploy.ps1 -Version 0.2
#

param(
    [string]$Version = "latest",
    [string]$AwsRegion = "eu-central-1",
    [switch]$SkipBuild,
    [switch]$SkipTerraform
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Write-Log {
    param([string]$Level, [string]$Message)
    $color = switch ($Level) {
        "INFO"  { "Green" }
        "WARN"  { "Yellow" }
        "ERROR" { "Red" }
        default { "White" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Test-Requirements {
    Write-Log "INFO" "Checking requirements..."

    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        Write-Log "ERROR" "AWS CLI is not installed. Please install it first."
        exit 1
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Log "ERROR" "Docker is not installed. Please install it first."
        exit 1
    }

    if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
        Write-Log "ERROR" "Terraform is not installed. Please install it first."
        exit 1
    }

    # Check AWS credentials
    try {
        aws sts get-caller-identity | Out-Null
    } catch {
        Write-Log "ERROR" "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    }

    Write-Log "INFO" "All requirements met."
}

function Get-EcrUrls {
    Write-Log "INFO" "Getting ECR repository URLs..."

    try {
        $script:BackendRepo = aws ecr describe-repositories --repository-names chatbot-backend --query 'repositories[0].repositoryUri' --output text 2>$null
        $script:FrontendRepo = aws ecr describe-repositories --repository-names chatbot-frontend --query 'repositories[0].repositoryUri' --output text 2>$null

        if (-not $BackendRepo -or -not $FrontendRepo) {
            throw "Repos not found"
        }

        Write-Log "INFO" "Backend ECR: $BackendRepo"
        Write-Log "INFO" "Frontend ECR: $FrontendRepo"
        return $true
    } catch {
        Write-Log "WARN" "ECR repositories not found. They will be created by Terraform."
        return $false
    }
}

function Invoke-EcrLogin {
    Write-Log "INFO" "Logging into ECR..."
    $AccountId = aws sts get-caller-identity --query Account --output text
    $Password = aws ecr get-login-password --region $AwsRegion
    $Password | docker login --username AWS --password-stdin "$AccountId.dkr.ecr.$AwsRegion.amazonaws.com"
}

function Build-Images {
    Write-Log "INFO" "Building Docker images with tag: $Version..."

    Push-Location $ProjectRoot

    try {
        # Build backend
        Write-Log "INFO" "Building backend image..."
        docker build -t "chatbot-backend:$Version" -f backend/Dockerfile backend/

        # Build frontend
        Write-Log "INFO" "Building frontend image..."
        docker build -t "chatbot-frontend:$Version" -f frontend/Dockerfile frontend/

        Write-Log "INFO" "Images built successfully."
    } finally {
        Pop-Location
    }
}

function Push-Images {
    Write-Log "INFO" "Pushing images to ECR..."

    # Tag images
    docker tag "chatbot-backend:$Version" "${BackendRepo}:$Version"
    docker tag "chatbot-frontend:$Version" "${FrontendRepo}:$Version"

    # Also tag as latest
    docker tag "chatbot-backend:$Version" "${BackendRepo}:latest"
    docker tag "chatbot-frontend:$Version" "${FrontendRepo}:latest"

    # Push images
    Write-Log "INFO" "Pushing backend image..."
    docker push "${BackendRepo}:$Version"
    docker push "${BackendRepo}:latest"

    Write-Log "INFO" "Pushing frontend image..."
    docker push "${FrontendRepo}:$Version"
    docker push "${FrontendRepo}:latest"

    Write-Log "INFO" "Images pushed successfully."
}

function Invoke-Terraform {
    Write-Log "INFO" "Applying Terraform with image_tag=$Version..."

    Push-Location "$ProjectRoot\terraform"

    try {
        # Initialize Terraform
        terraform init

        # Plan
        terraform plan -var="image_tag=$Version" -out=tfplan

        $response = Read-Host "Do you want to apply this plan? (y/n)"
        if ($response -eq 'y' -or $response -eq 'Y') {
            terraform apply tfplan
            Write-Log "INFO" "Terraform applied successfully."
        } else {
            Write-Log "WARN" "Terraform apply cancelled."
            exit 0
        }
    } finally {
        Pop-Location
    }
}

function Invoke-ForceDeployment {
    Write-Log "INFO" "Forcing new ECS deployment..."

    aws ecs update-service --cluster chatbot-cluster --service chatbot-backend --force-new-deployment --region $AwsRegion | Out-Null
    aws ecs update-service --cluster chatbot-cluster --service chatbot-frontend --force-new-deployment --region $AwsRegion | Out-Null

    Write-Log "INFO" "Deployment triggered. Monitor progress in AWS Console or with:"
    Write-Log "INFO" "  aws ecs describe-services --cluster chatbot-cluster --services chatbot-backend chatbot-frontend"
}

# Main
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Chatbot App Deployment - Version $Version" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host

Test-Requirements

if (Get-EcrUrls) {
    Invoke-EcrLogin

    if (-not $SkipBuild) {
        Build-Images
        Push-Images
    }

    if (-not $SkipTerraform) {
        Invoke-Terraform
    }

    Invoke-ForceDeployment
} else {
    Write-Log "INFO" "Running Terraform to create infrastructure first..."
    Push-Location "$ProjectRoot\terraform"
    try {
        terraform init
        terraform apply -var="image_tag=$Version"
    } finally {
        Pop-Location
    }

    Write-Log "INFO" "Infrastructure created. Run this script again to deploy images."
}

Write-Host
Write-Log "INFO" "==========================================="
Write-Log "INFO" "  Deployment Complete!"
Write-Log "INFO" "==========================================="
