#!/usr/bin/env bash
# rollback.sh — Manual emergency rollback for Azure Container Apps.
#
# Restores the previous revision to 100% traffic for one or all apps.
#
# Usage:
#   RESOURCE_GROUP=ironlayer-prod APP_PREFIX=ironlayer \
#   ./rollback.sh [api|ai|frontend|all]
#
# Defaults: TARGET=all
#
# Environment variables:
#   APP_PREFIX       — container app name prefix (default: ironlayer)
#   RESOURCE_GROUP   — Azure resource group (required; same variable as
#                      canary_deploy.sh for consistency)

set -euo pipefail

APP_PREFIX="${APP_PREFIX:-ironlayer}"
RG="${RESOURCE_GROUP:?RESOURCE_GROUP environment variable required}"
TARGET="${1:-all}"

# ---------------------------------------------------------------------------
# BL-083: Concurrency lock and cooldown guard.
#
# Prevents concurrent rollbacks and rapid successive rollbacks that could
# exhaust Azure Container Apps quota or leave traffic state inconsistent.
# ---------------------------------------------------------------------------
LOCK_FILE="/tmp/ironlayer-deploy-${APP_PREFIX}-rollback.lock"
STAMP_FILE="/tmp/ironlayer-deploy-${APP_PREFIX}-rollback.timestamp"
COOLDOWN_SECONDS=300  # 5-minute minimum between rollbacks

# Register cleanup on all exit paths before acquiring the lock.
trap "rm -f '${LOCK_FILE}'" EXIT INT TERM

# Check for concurrent rollback.
if [ -f "${LOCK_FILE}" ]; then
  LOCK_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "unknown")
  echo "ERROR: Another rollback is already in progress (PID ${LOCK_PID})." >&2
  echo "       Lock file: ${LOCK_FILE}" >&2
  exit 1
fi

# Check cooldown period.
if [ -f "${STAMP_FILE}" ]; then
  LAST_ROLLBACK=$(cat "${STAMP_FILE}" 2>/dev/null || echo "0")
  NOW=$(date +%s)
  ELAPSED=$(( NOW - LAST_ROLLBACK ))
  if [ "${ELAPSED}" -lt "${COOLDOWN_SECONDS}" ]; then
    REMAINING=$(( COOLDOWN_SECONDS - ELAPSED ))
    echo "ERROR: Cooldown period active. Last rollback was ${ELAPSED}s ago." >&2
    echo "       Wait ${REMAINING}s before rolling back again." >&2
    exit 1
  fi
fi

# Acquire lock.
echo $$ > "${LOCK_FILE}"

rollback_app() {
  local APP="$1"
  echo "─────────────────────────────────────────────────────────"
  echo "  Rolling back: ${APP}"

  # Find the second-most-recently created revision regardless of active state.
  # Azure Container Apps marks ALL deployed revisions as active=true until
  # they are explicitly deactivated, so filtering by properties.active would
  # return every revision — sorting by creation time and taking [-2] reliably
  # picks the one that was deployed before the current latest revision.
  PREV=$(az containerapp revision list \
    --name "$APP" \
    --resource-group "$RG" \
    --query "sort_by(@, &properties.createdTime)[-2].name" \
    --output tsv 2>/dev/null || echo "")

  if [ -z "$PREV" ]; then
    echo "  WARNING: No previous revision found for ${APP} — cannot roll back."
    return 1
  fi

  echo "  Restoring 100% traffic → ${PREV}"
  az containerapp ingress traffic set \
    --name "$APP" \
    --resource-group "$RG" \
    --revision-weight "${PREV}=100" \
    --output none

  CURRENT=$(az containerapp show \
    --name "$APP" \
    --resource-group "$RG" \
    --query "properties.latestRevisionName" \
    --output tsv 2>/dev/null || echo "unknown")

  echo "  ✓ ${APP}: ${CURRENT} → 0% traffic, ${PREV} → 100% traffic"
}

echo "═══════════════════════════════════════════════════════════"
echo "  IronLayer Emergency Rollback"
echo "  App prefix:     ${APP_PREFIX}"
echo "  Resource group: ${RG}"
echo "  Target:         ${TARGET}"
echo "═══════════════════════════════════════════════════════════"

case "$TARGET" in
  api)      rollback_app "${APP_PREFIX}-api" ;;
  ai)       rollback_app "${APP_PREFIX}-ai" ;;
  frontend) rollback_app "${APP_PREFIX}-frontend" ;;
  all)
    rollback_app "${APP_PREFIX}-api"
    rollback_app "${APP_PREFIX}-ai"
    rollback_app "${APP_PREFIX}-frontend"
    ;;
  *)
    echo "Usage: $0 [api|ai|frontend|all]"
    echo "  api       — rollback API only"
    echo "  ai        — rollback AI engine only"
    echo "  frontend  — rollback frontend only"
    echo "  all       — rollback all three services (default)"
    exit 1
    ;;
esac

# Record successful rollback timestamp for cooldown enforcement.
date +%s > "${STAMP_FILE}"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Rollback complete"
echo "═══════════════════════════════════════════════════════════"
