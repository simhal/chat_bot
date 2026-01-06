# =============================================================================
# Chatbot Application Test Runner (Windows PowerShell)
# =============================================================================
#
# Usage:
#   .\scripts\run-tests.ps1              # Run all tests (backend + frontend unit + e2e)
#   .\scripts\run-tests.ps1 -TestType backend      # Run only backend tests
#   .\scripts\run-tests.ps1 -TestType frontend     # Run only frontend tests
#   .\scripts\run-tests.ps1 -TestType e2e          # Run E2E tests with full stack
#   .\scripts\run-tests.ps1 -TestType unit         # Run backend unit tests only (fast)
#   .\scripts\run-tests.ps1 -TestType quick        # Run backend + frontend unit (no e2e)
#   .\scripts\run-tests.ps1 -Coverage              # Generate coverage reports
#
# =============================================================================

param(
    [ValidateSet("all", "backend", "frontend", "e2e", "unit", "integration", "quick")]
    [string]$TestType = "all",

    [switch]$Coverage,
    [switch]$Verbose,
    [switch]$KeepContainers,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

# Get project root (parent of scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Track test results
$BackendResult = 0
$FrontendResult = 0
$E2EResult = 0

Write-Host "======================================" -ForegroundColor Blue
Write-Host "   Chatbot Application Test Runner   " -ForegroundColor Blue
Write-Host "======================================" -ForegroundColor Blue
Write-Host ""
Write-Host "Project root: $ProjectRoot" -ForegroundColor Yellow
Write-Host "Test type:    $TestType" -ForegroundColor Yellow
Write-Host "Coverage:     $Coverage" -ForegroundColor Yellow
Write-Host ""

function Start-BaseContainers {
    Write-Host "Starting base test containers..." -ForegroundColor Blue

    Push-Location $ProjectRoot

    try {
        # Stop and remove existing test containers to ensure fresh data
        Write-Host "Removing existing test containers..."
        docker-compose -f docker-compose.test.yml down -v --remove-orphans 2>$null

        $buildArg = if (-not $NoBuild) { "--build" } else { "" }

        docker-compose -f docker-compose.test.yml up -d $buildArg postgres-test redis-test chroma-test

        Write-Host "Waiting for containers to be healthy..." -ForegroundColor Green

        # Wait for PostgreSQL
        Write-Host "Waiting for PostgreSQL..."
        for ($i = 1; $i -le 30; $i++) {
            try {
                $result = docker-compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U chatbot_test_user -d chatbot_test 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "PostgreSQL is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            if ($i -eq 30) {
                Write-Host "PostgreSQL failed to start" -ForegroundColor Red
                exit 1
            }
            Start-Sleep -Seconds 1
        }

        # Wait for Redis
        Write-Host "Waiting for Redis..."
        for ($i = 1; $i -le 30; $i++) {
            try {
                $result = docker-compose -f docker-compose.test.yml exec -T redis-test redis-cli ping 2>&1
                if ($result -match "PONG") {
                    Write-Host "Redis is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            if ($i -eq 30) {
                Write-Host "Redis failed to start" -ForegroundColor Red
                exit 1
            }
            Start-Sleep -Seconds 1
        }

        # Wait for ChromaDB
        Write-Host "Waiting for ChromaDB..."
        for ($i = 1; $i -le 30; $i++) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8002/api/v1/heartbeat" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Host "ChromaDB is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            if ($i -eq 30) {
                Write-Host "ChromaDB may not be ready, continuing..." -ForegroundColor Yellow
            }
            Start-Sleep -Seconds 1
        }

        Write-Host ""
    }
    finally {
        Pop-Location
    }
}

function Start-E2EStack {
    Write-Host "Starting E2E test stack (backend + frontend + celery)..." -ForegroundColor Blue

    Push-Location $ProjectRoot

    try {
        $buildArg = if (-not $NoBuild) { "--build" } else { "" }

        docker-compose -f docker-compose.test.yml --profile e2e up -d $buildArg backend-e2e celery-worker-test frontend-test

        # Wait for backend
        Write-Host "Waiting for backend API to be ready..."
        for ($i = 1; $i -le 60; $i++) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Host "Backend API is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            if ($i -eq 60) {
                Write-Host "Backend failed to start within 2 minutes" -ForegroundColor Red
                docker-compose -f docker-compose.test.yml logs backend-e2e
                exit 1
            }
            Start-Sleep -Seconds 2
        }

        # Wait for frontend
        Write-Host "Waiting for frontend to be ready..."
        for ($i = 1; $i -le 30; $i++) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Host "Frontend is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            if ($i -eq 30) {
                Write-Host "Frontend failed to start within 1 minute" -ForegroundColor Red
                docker-compose -f docker-compose.test.yml logs frontend-test
                exit 1
            }
            Start-Sleep -Seconds 2
        }

        Write-Host ""
    }
    finally {
        Pop-Location
    }
}

function Stop-TestContainers {
    Push-Location $ProjectRoot

    try {
        if (-not $KeepContainers) {
            Write-Host "Stopping test containers..." -ForegroundColor Blue
            docker-compose -f docker-compose.test.yml --profile e2e down -v 2>$null
        } else {
            Write-Host "Keeping test containers running" -ForegroundColor Yellow
            Write-Host "To stop: docker-compose -f docker-compose.test.yml --profile e2e down -v"
        }
    }
    catch {
        # Ignore errors during cleanup
    }
    finally {
        Pop-Location
    }
}

function Run-BackendTests {
    $marker = switch ($TestType) {
        "unit" { "-m unit" }
        "integration" { "-m integration" }
        default { "" }
    }

    $coverageArgs = if ($Coverage) { "--cov=. --cov-report=html --cov-report=term-missing" } else { "" }

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Running Backend Tests (pytest)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    # Set environment variables
    $env:DATABASE_URL = "postgresql://chatbot_test_user:chatbot_test_password@localhost:5433/chatbot_test"
    $env:REDIS_URL = "redis://localhost:6380/0"
    $env:REDIS_HOST = "localhost"
    $env:REDIS_PORT = "6380"
    $env:CHROMA_HOST = "localhost"
    $env:CHROMA_PORT = "8002"
    $env:TESTING = "true"
    $env:JWT_SECRET_KEY = "test-secret-key-for-testing-only"
    $env:JWT_ALGORITHM = "HS256"

    Push-Location "$ProjectRoot\backend"

    try {
        # Sync dependencies
        Write-Host "Syncing dependencies..."
        uv sync --extra test

        # Run migrations
        Write-Host "Running database migrations..."
        uv run alembic upgrade head

        # Run tests
        Write-Host ""
        Write-Host "Running pytest..."
        $verboseArg = if ($Verbose) { "-v --tb=long" } else { "--tb=short" }

        # Build the pytest command
        $pytestArgs = @("tests/", $verboseArg)
        if ($marker) { $pytestArgs += $marker }
        if ($coverageArgs) { $pytestArgs += $coverageArgs }

        uv run pytest @pytestArgs
        $script:BackendResult = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($script:BackendResult -eq 0) {
        Write-Host "Backend tests passed!" -ForegroundColor Green
    } else {
        Write-Host "Backend tests failed!" -ForegroundColor Red
    }
    Write-Host ""
}

function Run-FrontendUnitTests {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Running Frontend Unit Tests (vitest)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    Push-Location "$ProjectRoot\frontend"

    try {
        Write-Host "Installing frontend dependencies..."
        npm ci

        Write-Host "Running vitest..."
        if ($Coverage) {
            npm run test:run -- --coverage
        } else {
            npm run test:run
        }
        $script:FrontendResult = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($script:FrontendResult -eq 0) {
        Write-Host "Frontend unit tests passed!" -ForegroundColor Green
    } else {
        Write-Host "Frontend unit tests failed!" -ForegroundColor Red
    }
    Write-Host ""
}

function Run-E2ETests {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Running E2E Tests (Playwright)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    Push-Location "$ProjectRoot\frontend"

    try {
        # Install dependencies if not already done
        if (-not (Test-Path "node_modules")) {
            Write-Host "Installing frontend dependencies..."
            npm ci
        }

        Write-Host "Installing Playwright browsers..."
        npx playwright install chromium

        Write-Host "Running Playwright E2E tests..."
        $env:BASE_URL = "http://localhost:3000"
        $env:API_URL = "http://localhost:8000"
        npx playwright test --reporter=html
        $script:E2EResult = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($script:E2EResult -eq 0) {
        Write-Host "E2E tests passed!" -ForegroundColor Green
    } else {
        Write-Host "E2E tests failed!" -ForegroundColor Red
    }
    Write-Host "E2E report available at: frontend/playwright-report/index.html"
    Write-Host ""
}

function Run-AllTests {
    Run-BackendTests
    Run-FrontendUnitTests
    Start-E2EStack
    Run-E2ETests
}

function Run-QuickTests {
    Run-BackendTests
    Run-FrontendUnitTests
}

# Main execution
try {
    switch ($TestType) {
        "all" {
            Start-BaseContainers
            Run-AllTests
        }
        "quick" {
            Start-BaseContainers
            Run-QuickTests
        }
        { $_ -in "backend", "unit", "integration" } {
            Start-BaseContainers
            Run-BackendTests
        }
        "frontend" {
            Run-FrontendUnitTests
        }
        "e2e" {
            Start-BaseContainers
            Start-E2EStack
            Run-E2ETests
        }
    }

    # Print summary
    Write-Host ""
    Write-Host "======================================" -ForegroundColor Blue
    Write-Host "           Test Summary" -ForegroundColor Blue
    Write-Host "======================================" -ForegroundColor Blue

    $TotalFailed = 0

    if ($TestType -in "all", "quick", "backend", "unit", "integration") {
        if ($BackendResult -eq 0) {
            Write-Host "Backend:  PASSED" -ForegroundColor Green
        } else {
            Write-Host "Backend:  FAILED" -ForegroundColor Red
            $TotalFailed++
        }
    }

    if ($TestType -in "all", "quick", "frontend") {
        if ($FrontendResult -eq 0) {
            Write-Host "Frontend: PASSED" -ForegroundColor Green
        } else {
            Write-Host "Frontend: FAILED" -ForegroundColor Red
            $TotalFailed++
        }
    }

    if ($TestType -in "all", "e2e") {
        if ($E2EResult -eq 0) {
            Write-Host "E2E:      PASSED" -ForegroundColor Green
        } else {
            Write-Host "E2E:      FAILED" -ForegroundColor Red
            $TotalFailed++
        }
    }

    Write-Host ""

    if ($TotalFailed -eq 0) {
        Write-Host "======================================" -ForegroundColor Green
        Write-Host "   All tests completed successfully!  " -ForegroundColor Green
        Write-Host "======================================" -ForegroundColor Green
    } else {
        Write-Host "======================================" -ForegroundColor Red
        Write-Host "   Some tests failed!" -ForegroundColor Red
        Write-Host "======================================" -ForegroundColor Red
        exit 1
    }
}
finally {
    Stop-TestContainers
}
