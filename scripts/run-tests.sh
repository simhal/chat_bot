#!/bin/bash

# =============================================================================
# Chatbot Application Test Runner
# =============================================================================
#
# Usage:
#   ./scripts/run-tests.sh              # Run all tests (backend + frontend unit + e2e)
#   ./scripts/run-tests.sh backend      # Run only backend tests
#   ./scripts/run-tests.sh frontend     # Run only frontend unit tests
#   ./scripts/run-tests.sh e2e          # Run only E2E tests with full stack
#   ./scripts/run-tests.sh unit         # Run backend unit tests only (fast)
#   ./scripts/run-tests.sh integration  # Run backend integration tests only
#   ./scripts/run-tests.sh quick        # Run backend + frontend unit only (no e2e)
#
# Options:
#   --coverage    Generate coverage reports
#   --verbose     Verbose output
#   --keep        Keep containers running after tests
#   --no-build    Skip rebuilding containers
#
# =============================================================================

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
COVERAGE=false
VERBOSE=false
KEEP_CONTAINERS=false
NO_BUILD=false
TEST_TYPE="all"

# Track test results
BACKEND_RESULT=0
FRONTEND_RESULT=0
E2E_RESULT=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        backend|frontend|e2e|unit|integration|quick|all)
            TEST_TYPE="$1"
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --keep)
            KEEP_CONTAINERS=true
            shift
            ;;
        --no-build)
            NO_BUILD=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [test-type] [options]"
            echo ""
            echo "Test types:"
            echo "  all          Run all tests (backend + frontend unit + e2e) [default]"
            echo "  backend      Run only backend pytest tests"
            echo "  frontend     Run only frontend unit tests (vitest)"
            echo "  e2e          Run only Playwright E2E tests"
            echo "  unit         Run backend unit tests only (marked with @pytest.mark.unit)"
            echo "  integration  Run backend integration tests only"
            echo "  quick        Run backend + frontend unit tests only (no e2e)"
            echo ""
            echo "Options:"
            echo "  --coverage   Generate coverage reports"
            echo "  --verbose    Verbose output"
            echo "  --keep       Keep containers running after tests"
            echo "  --no-build   Skip rebuilding containers"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   Chatbot Application Test Runner   ${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""
echo -e "Project root: ${YELLOW}$PROJECT_ROOT${NC}"
echo -e "Test type:    ${YELLOW}$TEST_TYPE${NC}"
echo -e "Coverage:     ${YELLOW}$COVERAGE${NC}"
echo ""

# Function to start base test containers (postgres, redis, chroma)
start_base_containers() {
    echo -e "${BLUE}Starting base test containers...${NC}"

    cd "$PROJECT_ROOT"

    # Stop and remove existing test containers to ensure fresh data
    echo "Removing existing test containers..."
    docker-compose -f docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true

    local BUILD_ARG=""
    if [ "$NO_BUILD" = false ]; then
        BUILD_ARG="--build"
    fi

    docker-compose -f docker-compose.test.yml up -d $BUILD_ARG postgres-test redis-test chroma-test

    echo -e "${GREEN}Waiting for containers to be healthy...${NC}"

    # Wait for PostgreSQL
    echo "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if docker-compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U chatbot_test_user -d chatbot_test > /dev/null 2>&1; then
            echo -e "${GREEN}PostgreSQL is ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}PostgreSQL failed to start${NC}"
            exit 1
        fi
        sleep 1
    done

    # Wait for Redis
    echo "Waiting for Redis..."
    for i in {1..30}; do
        if docker-compose -f docker-compose.test.yml exec -T redis-test redis-cli ping 2>/dev/null | grep -q PONG; then
            echo -e "${GREEN}Redis is ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}Redis failed to start${NC}"
            exit 1
        fi
        sleep 1
    done

    # Wait for ChromaDB
    echo "Waiting for ChromaDB..."
    for i in {1..30}; do
        if curl -s http://localhost:8002/api/v1/heartbeat > /dev/null 2>&1; then
            echo -e "${GREEN}ChromaDB is ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${YELLOW}ChromaDB may not be ready, continuing...${NC}"
        fi
        sleep 1
    done

    echo ""
}

# Function to start E2E test stack
start_e2e_stack() {
    echo -e "${BLUE}Starting E2E test stack (backend + frontend + celery)...${NC}"

    cd "$PROJECT_ROOT"

    local BUILD_ARG=""
    if [ "$NO_BUILD" = false ]; then
        BUILD_ARG="--build"
    fi

    docker-compose -f docker-compose.test.yml --profile e2e up -d $BUILD_ARG backend-e2e celery-worker-test frontend-test

    # Wait for backend to be healthy
    echo "Waiting for backend API to be ready..."
    for i in {1..60}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}Backend API is ready!${NC}"
            break
        fi
        if [ $i -eq 60 ]; then
            echo -e "${RED}Backend failed to start within 2 minutes${NC}"
            docker-compose -f docker-compose.test.yml logs backend-e2e
            exit 1
        fi
        sleep 2
    done

    # Wait for frontend to be ready
    echo "Waiting for frontend to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:3000 > /dev/null 2>&1; then
            echo -e "${GREEN}Frontend is ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}Frontend failed to start within 1 minute${NC}"
            docker-compose -f docker-compose.test.yml logs frontend-test
            exit 1
        fi
        sleep 2
    done

    echo ""
}

# Function to stop test containers
stop_test_containers() {
    cd "$PROJECT_ROOT"
    if [ "$KEEP_CONTAINERS" = false ]; then
        echo -e "${BLUE}Stopping test containers...${NC}"
        docker-compose -f docker-compose.test.yml --profile e2e down -v 2>/dev/null || true
    else
        echo -e "${YELLOW}Keeping test containers running${NC}"
        echo "To stop: docker-compose -f docker-compose.test.yml --profile e2e down -v"
    fi
}

# Function to run backend tests
run_backend_tests() {
    local marker=""
    local coverage_args=""

    case $TEST_TYPE in
        unit)
            marker="-m unit"
            ;;
        integration)
            marker="-m integration"
            ;;
    esac

    if [ "$COVERAGE" = true ]; then
        coverage_args="--cov=. --cov-report=html --cov-report=term-missing"
    fi

    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Running Backend Tests (pytest)${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""

    # Set environment variables for test database
    export DATABASE_URL="postgresql://chatbot_test_user:chatbot_test_password@localhost:5433/chatbot_test"
    export REDIS_URL="redis://localhost:6380/0"
    export REDIS_HOST="localhost"
    export REDIS_PORT="6380"
    export CHROMA_HOST="localhost"
    export CHROMA_PORT="8002"
    export TESTING="true"
    export JWT_SECRET_KEY="test-secret-key-for-testing-only"
    export JWT_ALGORITHM="HS256"

    cd "$PROJECT_ROOT/backend"

    # Sync dependencies
    echo "Syncing dependencies..."
    uv sync --extra test

    # Run migrations
    echo "Running database migrations..."
    uv run alembic upgrade head

    # Run tests
    echo ""
    echo "Running pytest..."
    if [ "$VERBOSE" = true ]; then
        uv run pytest tests/ -v --tb=long $marker $coverage_args || BACKEND_RESULT=$?
    else
        uv run pytest tests/ --tb=short $marker $coverage_args || BACKEND_RESULT=$?
    fi

    cd "$PROJECT_ROOT"

    if [ $BACKEND_RESULT -eq 0 ]; then
        echo -e "${GREEN}Backend tests passed!${NC}"
    else
        echo -e "${RED}Backend tests failed!${NC}"
    fi
    echo ""
}

# Function to run frontend unit tests
run_frontend_unit_tests() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Running Frontend Unit Tests (vitest)${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""

    cd "$PROJECT_ROOT/frontend"

    # Install dependencies
    echo "Installing frontend dependencies..."
    npm ci

    # Run vitest
    echo "Running vitest..."
    if [ "$COVERAGE" = true ]; then
        npm run test:run -- --coverage || FRONTEND_RESULT=$?
    else
        npm run test:run || FRONTEND_RESULT=$?
    fi

    cd "$PROJECT_ROOT"

    if [ $FRONTEND_RESULT -eq 0 ]; then
        echo -e "${GREEN}Frontend unit tests passed!${NC}"
    else
        echo -e "${RED}Frontend unit tests failed!${NC}"
    fi
    echo ""
}

# Function to run E2E tests
run_e2e_tests() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Running E2E Tests (Playwright)${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""

    cd "$PROJECT_ROOT/frontend"

    # Install dependencies if not already done
    if [ ! -d "node_modules" ]; then
        echo "Installing frontend dependencies..."
        npm ci
    fi

    # Install Playwright browsers if needed
    echo "Installing Playwright browsers..."
    npx playwright install chromium

    # Run E2E tests
    echo "Running Playwright E2E tests..."
    BASE_URL="http://localhost:3000" API_URL="http://localhost:8000" npx playwright test --reporter=html || E2E_RESULT=$?

    cd "$PROJECT_ROOT"

    if [ $E2E_RESULT -eq 0 ]; then
        echo -e "${GREEN}E2E tests passed!${NC}"
    else
        echo -e "${RED}E2E tests failed!${NC}"
    fi
    echo "E2E report available at: frontend/playwright-report/index.html"
    echo ""
}

# Function to run all tests
run_all_tests() {
    # Run backend tests first
    run_backend_tests

    # Run frontend unit tests
    run_frontend_unit_tests

    # Start E2E stack and run E2E tests
    start_e2e_stack
    run_e2e_tests
}

# Function to run quick tests (no e2e)
run_quick_tests() {
    run_backend_tests
    run_frontend_unit_tests
}

# Trap to ensure cleanup on exit
trap stop_test_containers EXIT

# Main execution
case $TEST_TYPE in
    all)
        start_base_containers
        run_all_tests
        ;;
    quick)
        start_base_containers
        run_quick_tests
        ;;
    backend|unit|integration)
        start_base_containers
        run_backend_tests
        ;;
    frontend)
        run_frontend_unit_tests
        ;;
    e2e)
        start_base_containers
        start_e2e_stack
        run_e2e_tests
        ;;
esac

# Print summary
echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}           Test Summary${NC}"
echo -e "${BLUE}======================================${NC}"

TOTAL_FAILED=0

if [ "$TEST_TYPE" = "all" ] || [ "$TEST_TYPE" = "quick" ] || [ "$TEST_TYPE" = "backend" ] || [ "$TEST_TYPE" = "unit" ] || [ "$TEST_TYPE" = "integration" ]; then
    if [ $BACKEND_RESULT -eq 0 ]; then
        echo -e "Backend:  ${GREEN}PASSED${NC}"
    else
        echo -e "Backend:  ${RED}FAILED${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

if [ "$TEST_TYPE" = "all" ] || [ "$TEST_TYPE" = "quick" ] || [ "$TEST_TYPE" = "frontend" ]; then
    if [ $FRONTEND_RESULT -eq 0 ]; then
        echo -e "Frontend: ${GREEN}PASSED${NC}"
    else
        echo -e "Frontend: ${RED}FAILED${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

if [ "$TEST_TYPE" = "all" ] || [ "$TEST_TYPE" = "e2e" ]; then
    if [ $E2E_RESULT -eq 0 ]; then
        echo -e "E2E:      ${GREEN}PASSED${NC}"
    else
        echo -e "E2E:      ${RED}FAILED${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

echo ""

if [ $TOTAL_FAILED -eq 0 ]; then
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}   All tests completed successfully!  ${NC}"
    echo -e "${GREEN}======================================${NC}"
    exit 0
else
    echo -e "${RED}======================================${NC}"
    echo -e "${RED}   Some tests failed!${NC}"
    echo -e "${RED}======================================${NC}"
    exit 1
fi
