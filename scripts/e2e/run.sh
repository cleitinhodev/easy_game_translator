#!/usr/bin/env bash
# Roda o Electron sob xvfb e salva screenshots em $EGT_SHOTS (padrão ./screenshots).
set -e
cd "$(dirname "$0")/../.."
export EGT_USER_DATA=${EGT_USER_DATA:-/tmp/egt_ud} EGT_CONFIG_DIR=${EGT_CONFIG_DIR:-/tmp/egt_cfg}
rm -rf "$EGT_USER_DATA" "$EGT_CONFIG_DIR"
export EGT_SHOTS=${EGT_SHOTS:-$PWD/screenshots} EGT_E2E="$PWD/scripts/e2e/${1:-shots.cjs}" EGT_DEMO=1 EGT_NO_GPU=1 ELECTRON_DISABLE_SECURITY_WARNINGS=1
exec xvfb-run -a -s "-screen 0 1600x1000x24" npx electron --no-sandbox --disable-gpu --disable-dev-shm-usage .
