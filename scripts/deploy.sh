#!/usr/bin/env bash
# Собрать панель и выложить на Cloudflare Pages.
# Нужны переменные окружения: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID.
# Необязательные: DIGEST_DIR, PANEL_CONFIG_DIR, CF_PAGES_PROJECT (по умолчанию viled-agents).
set -euo pipefail
cd "$(dirname "$0")/.."
DIGEST_DIR="${DIGEST_DIR:-/mnt/project-files/ecom-digest}"
PANEL_CONFIG_DIR="${PANEL_CONFIG_DIR:-/mnt/project-files/agents-panel/config}"
PROJECT="${CF_PAGES_PROJECT:-viled-agents}"

python3 -m panel.build --digest-dir "$DIGEST_DIR" --config-dir "$PANEL_CONFIG_DIR" --out dist
npx --yes wrangler@3 pages deploy dist --project-name "$PROJECT" --branch main --commit-dirty=true
