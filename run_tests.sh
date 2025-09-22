#!/bin/bash

echo "🧪 Local Memory MCP - Test Runner"
echo "================================="
echo ""

# Activate virtual environment
source venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Function to run different test suites
run_unit_tests() {
    echo "📦 Running Unit Tests..."
    pytest test_e2e.py::test_database_connection -v
    pytest test_e2e.py::test_pgvector_extension -v
    pytest test_e2e.py::test_memory_table_exists -v
}

run_integration_tests() {
    echo "🔗 Running Integration Tests..."
    pytest test_e2e.py::test_insert_and_search_memory -v
    pytest test_e2e.py::test_consolidator -v
    pytest test_e2e.py::test_memory_scorer -v
}

run_api_tests() {
    echo "🌐 Running API Tests..."

    # Test with httpie if installed
    if command -v http &> /dev/null; then
        echo "Testing with HTTPie..."
        # Test health endpoint
        http GET localhost:8443/api/health --verify=no 2>/dev/null || echo "API not running"
    fi

    # Test with curl as fallback
    echo "Testing with curl..."
    curl -s http://localhost:11434/api/tags | jq '.models[]?.name' 2>/dev/null || echo "Ollama not running"
}

run_load_tests() {
    echo "⚡ Running Load Tests with Locust..."
    echo "Visit http://localhost:8089 to start load test"
    locust -f locustfile.py --host=http://localhost:8443
}

run_all_tests() {
    echo "🏁 Running ALL Tests..."
    pytest test_e2e.py -v --tb=short --cov=src --cov-report=term-missing
}

# Parse command line arguments
case "$1" in
    unit)
        run_unit_tests
        ;;
    integration)
        run_integration_tests
        ;;
    api)
        run_api_tests
        ;;
    load)
        run_load_tests
        ;;
    all)
        run_all_tests
        ;;
    *)
        echo "Usage: $0 {unit|integration|api|load|all}"
        echo ""
        echo "Options:"
        echo "  unit        - Run unit tests (database connectivity)"
        echo "  integration - Run integration tests (memory operations)"
        echo "  api         - Test API endpoints with HTTPie/curl"
        echo "  load        - Run load tests with Locust"
        echo "  all         - Run all tests with coverage report"
        echo ""
        echo "Example: $0 all"
        ;;
esac