#!/usr/bin/env bash
# =============================================================================
# IronLayer End-to-End Smoke Test
#
# Verifies critical paths in the production deployment.
# Usage: ./scripts/e2e_smoke_test.sh [BASE_URL]
# Default: https://api.ironlayer.app
# =============================================================================

set -euo pipefail

BASE_URL="${1:-https://api.ironlayer.app}"
FRONTEND_URL="${2:-https://app.ironlayer.app}"
MARKETING_URL="${3:-https://ironlayer.app}"
PASS=0
FAIL=0
WARN=0

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[0;33m%s\033[0m\n' "$*"; }
blue()  { printf '\033[0;34m%s\033[0m\n' "$*"; }

check() {
    local desc="$1" cmd="$2" expected="$3"
    local result
    result=$(eval "$cmd" 2>/dev/null) || result="ERROR"
    if echo "$result" | grep -q "$expected"; then
        green "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        red "  ✗ $desc (expected: $expected, got: $result)"
        FAIL=$((FAIL + 1))
    fi
}

check_status() {
    local desc="$1" url="$2" expected_code="$3"
    local status
    status=$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null) || status="000"
    if [ "$status" = "$expected_code" ]; then
        green "  ✓ $desc (HTTP $status)"
        PASS=$((PASS + 1))
    else
        red "  ✗ $desc (expected HTTP $expected_code, got HTTP $status)"
        FAIL=$((FAIL + 1))
    fi
}

check_ssl() {
    local desc="$1" host="$2"
    local expiry
    expiry=$(echo | openssl s_client -connect "${host}:443" -servername "$host" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2) || expiry=""
    if [ -n "$expiry" ]; then
        local expiry_epoch
        expiry_epoch=$(date -j -f "%b %d %H:%M:%S %Y %Z" "$expiry" +%s 2>/dev/null || date -d "$expiry" +%s 2>/dev/null) || expiry_epoch=0
        local now_epoch
        now_epoch=$(date +%s)
        local days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
        if [ "$days_left" -gt 14 ]; then
            green "  ✓ $desc (expires: $expiry, ${days_left} days left)"
            PASS=$((PASS + 1))
        elif [ "$days_left" -gt 0 ]; then
            yellow "  ⚠ $desc (expires in ${days_left} days — renew soon!)"
            WARN=$((WARN + 1))
        else
            red "  ✗ $desc (EXPIRED: $expiry)"
            FAIL=$((FAIL + 1))
        fi
    else
        red "  ✗ $desc (could not read certificate)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
blue "═══════════════════════════════════════════════════════════════"
blue "  IronLayer Production Smoke Test"
blue "  API:       $BASE_URL"
blue "  Frontend:  $FRONTEND_URL"
blue "  Marketing: $MARKETING_URL"
blue "  Time:      $(date -u +%Y-%m-%dT%H:%M:%SZ)"
blue "═══════════════════════════════════════════════════════════════"

# -------------------------------------------------------------------------
echo ""
blue "1. SSL Certificates"
# -------------------------------------------------------------------------
check_ssl "API SSL cert" "api.ironlayer.app"
check_ssl "App SSL cert" "app.ironlayer.app"
check_ssl "Marketing SSL cert" "ironlayer.app"

# -------------------------------------------------------------------------
echo ""
blue "2. Infrastructure Health"
# -------------------------------------------------------------------------
check_status "API health endpoint" "$BASE_URL/api/v1/health" "200"
check "API returns healthy status" "curl -s $BASE_URL/api/v1/health" '"status":"healthy"'
check "API database connection" "curl -s $BASE_URL/api/v1/health" '"db":"ok"'
check_status "Frontend serves HTML" "$FRONTEND_URL" "200"
check_status "Marketing site loads" "$MARKETING_URL" "200"

# -------------------------------------------------------------------------
echo ""
blue "3. CORS Headers"
# -------------------------------------------------------------------------
check "CORS allows app.ironlayer.app" \
    "curl -s -H 'Origin: https://app.ironlayer.app' -I $BASE_URL/api/v1/health | grep -i access-control-allow-origin" \
    "app.ironlayer.app"

# -------------------------------------------------------------------------
echo ""
blue "4. Rate Limiting"
# -------------------------------------------------------------------------
check "Rate limit headers present" \
    "curl -s -I $BASE_URL/api/v1/health | grep -i x-ratelimit-limit" \
    "ratelimit-limit"

# -------------------------------------------------------------------------
echo ""
blue "5. Auth Endpoints"
# -------------------------------------------------------------------------
# Test that auth endpoints exist and return proper errors for bad input
check_status "Login endpoint exists" "$BASE_URL/api/v1/auth/login" "405"
check "Signup rejects empty body" \
    "curl -s -X POST -H 'Content-Type: application/json' -d '{}' $BASE_URL/api/v1/auth/signup | head -c 200" \
    "detail"

# -------------------------------------------------------------------------
echo ""
blue "6. Protected Endpoints (require auth)"
# -------------------------------------------------------------------------
check "Plans returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/plans" \
    "401"
check "Models returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/models" \
    "401"
check "Runs returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/runs" \
    "401"
check "Settings returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/settings" \
    "401"
check "Environments returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/environments" \
    "401"

# -------------------------------------------------------------------------
echo ""
blue "7. Billing Endpoints"
# -------------------------------------------------------------------------
check "Billing subscription returns 401 without auth" \
    "curl -s -o /dev/null -w '%{http_code}' $BASE_URL/api/v1/billing/subscription" \
    "401"

# -------------------------------------------------------------------------
echo ""
blue "8. Prometheus Metrics"
# -------------------------------------------------------------------------
check_status "Metrics endpoint accessible" "$BASE_URL/metrics" "200"
check "Metrics endpoint returns Prometheus data" \
    "curl -s $BASE_URL/metrics | head -5" \
    "python"

# -------------------------------------------------------------------------
echo ""
blue "═══════════════════════════════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    green "  RESULT: ALL $PASS CHECKS PASSED ($WARN warnings)"
else
    red "  RESULT: $FAIL FAILED, $PASS passed, $WARN warnings"
fi
blue "═══════════════════════════════════════════════════════════════"
echo ""

exit $FAIL
