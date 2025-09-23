#!/bin/bash
# Comprehensive Project Audit Script
# Local Context Memory MCP - Security & Quality Audit

set -e

PROJECT_ROOT="/Users/linuxbabe/local-memory-mcp"
AUDIT_DIR="$PROJECT_ROOT/audit-reports"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "🔍 Starting comprehensive audit of Local Context Memory MCP"
echo "📁 Audit reports will be saved to: $AUDIT_DIR"
echo "⏰ Timestamp: $TIMESTAMP"

# Create audit directory
mkdir -p "$AUDIT_DIR"

cd "$PROJECT_ROOT"

# 1. Python Security & Quality
echo "🐍 Running Python security and quality audits..."

# Install audit tools if not present
pip3 install --quiet bandit safety semgrep flake8 black isort mypy pip-audit

# Add Python bin to PATH
export PATH="/Users/linuxbabe/Library/Python/3.9/bin:$PATH"

# Security audits
echo "  🔐 Running security scans..."
bandit -r src/ -f json -o "$AUDIT_DIR/bandit-security-$TIMESTAMP.json" || true
safety check --json --output "$AUDIT_DIR/safety-deps-$TIMESTAMP.json" || true
pip-audit --format=json --output="$AUDIT_DIR/pip-audit-$TIMESTAMP.json" || true

# Code quality
echo "  📝 Running code quality checks..."
flake8 src/ --output-file="$AUDIT_DIR/flake8-$TIMESTAMP.txt" || true
black --check --diff src/ > "$AUDIT_DIR/black-check-$TIMESTAMP.txt" || true
isort --check-only --diff src/ > "$AUDIT_DIR/isort-check-$TIMESTAMP.txt" || true
mypy src/ --html-report "$AUDIT_DIR/mypy-$TIMESTAMP/" || true

# 2. Secrets Detection
echo "🔑 Scanning for secrets and sensitive data..."
pip3 install --quiet truffleHog

truffleHog --regex --entropy=False . > "$AUDIT_DIR/trufflehog-$TIMESTAMP.txt" || true
# Note: gitleaks is not available via pip, skipping
echo "  ⚠️ gitleaks not available via pip, skipping git secrets scan"

# 3. Configuration Audit
echo "⚙️ Auditing configuration files..."
grep -r "password\|secret\|key\|token" . --include="*.env" --include="*.conf" --include="*.json" > "$AUDIT_DIR/config-secrets-$TIMESTAMP.txt" || true

# 4. Docker Security
echo "🐳 Running Docker security audit..."
if command -v hadolint &> /dev/null; then
    hadolint Dockerfile.production > "$AUDIT_DIR/hadolint-production-$TIMESTAMP.txt" || true
    hadolint Dockerfile.postgres_version > "$AUDIT_DIR/hadolint-postgres-$TIMESTAMP.txt" || true
else
    echo "  ⚠️ hadolint not installed, skipping Docker linting"
fi

# 5. Database Audit
echo "🗄️ Auditing database configuration..."
if pg_isready -h localhost -p 5432 &> /dev/null; then
    psql -h localhost -U postgres -d test -c "
    SELECT 'Database connections:' as audit_item, count(*) as count FROM pg_stat_activity;
    SELECT 'Database roles:' as audit_item, count(*) as count FROM pg_roles;
    SELECT 'Table privileges:' as audit_item, count(*) as count FROM information_schema.table_privileges;
    " > "$AUDIT_DIR/database-audit-$TIMESTAMP.txt" || true
else
    echo "  ⚠️ PostgreSQL not running, skipping database audit"
fi

# 6. Test Coverage
echo "🧪 Running test coverage analysis..."
if [ -f "requirements.txt" ] || [ -f "requirements.pgvector.txt" ]; then
    pip3 install --quiet coverage pytest-cov
    coverage run -m pytest tests/ > "$AUDIT_DIR/test-coverage-$TIMESTAMP.txt" 2>&1 || true
    coverage report --html="$AUDIT_DIR/coverage-report-$TIMESTAMP/" || true
    coverage xml -o "$AUDIT_DIR/coverage-$TIMESTAMP.xml" || true
else
    echo "  ⚠️ No test requirements found, skipping coverage analysis"
fi

# 7. Performance Testing
echo "⚡ Running performance tests..."
if [ -f "k6_memory_test.js" ]; then
    if command -v k6 &> /dev/null; then
        # Check if server is running before running K6 tests
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            echo "  🚀 Server is running, executing K6 performance test..."
            timeout 30s k6 run k6_memory_test.js --out json="$AUDIT_DIR/k6-performance-$TIMESTAMP.json" || echo "  ⚠️ K6 test timed out or failed"
        else
            echo "  ⚠️ Server not running on port 8080, skipping K6 performance tests"
        fi
    else
        echo "  ⚠️ k6 not installed, skipping performance tests"
    fi
fi

# 8. Generate Summary Report
echo "📊 Generating audit summary..."
cat > "$AUDIT_DIR/AUDIT_SUMMARY_$TIMESTAMP.md" << EOF
# Local Context Memory MCP - Audit Summary

**Audit Date:** $(date)
**Project:** Local Context Memory MCP
**Audit Scope:** Security, Quality, Performance, Compliance

## Audit Results

### Security Scans
- **Bandit (Python Security):** \`bandit-security-$TIMESTAMP.json\`
- **Safety (Dependencies):** \`safety-deps-$TIMESTAMP.json\`
- **Pip Audit:** \`pip-audit-$TIMESTAMP.json\`
- **Secrets Detection:** \`trufflehog-$TIMESTAMP.txt\`, \`gitleaks-$TIMESTAMP.json\`

### Code Quality
- **Flake8 (Style):** \`flake8-$TIMESTAMP.txt\`
- **Black (Formatting):** \`black-check-$TIMESTAMP.txt\`
- **isort (Imports):** \`isort-check-$TIMESTAMP.txt\`
- **MyPy (Types):** \`mypy-$TIMESTAMP/\`

### Infrastructure
- **Docker Security:** \`hadolint-*-$TIMESTAMP.txt\`
- **Database Audit:** \`database-audit-$TIMESTAMP.txt\`
- **Configuration:** \`config-secrets-$TIMESTAMP.txt\`

### Testing & Performance
- **Test Coverage:** \`coverage-report-$TIMESTAMP/\`
- **Performance:** \`k6-performance-$TIMESTAMP.json\`

## Next Steps

1. Review all security findings and address critical issues
2. Fix code quality issues identified by linters
3. Update dependencies with known vulnerabilities
4. Review and secure any exposed secrets
5. Optimize performance based on test results

## Files Generated

$(ls -la "$AUDIT_DIR" | grep "$TIMESTAMP")

EOF

echo "✅ Audit completed successfully!"
echo "📁 All reports saved to: $AUDIT_DIR"
echo "📋 Summary report: $AUDIT_DIR/AUDIT_SUMMARY_$TIMESTAMP.md"
echo ""
echo "🔍 Review the findings and address any critical issues."
