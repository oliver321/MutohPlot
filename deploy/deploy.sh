#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-$(pwd)}"
APP_HOME="${MUTOHPLOT_APP_HOME:-$HOME/.local/share/mutohplot}"
RELEASES_DIR="$APP_HOME/releases"
CURRENT_LINK="$APP_HOME/current"
BACKUP_DIR="$APP_HOME/backups"
LEGACY_DIR="${MUTOHPLOT_LEGACY_DIR:-$HOME/MutohPlot-web}"
SERVICE_NAME="${MUTOHPLOT_SERVICE_NAME:-mutohplot-web.service}"
HEALTH_URL="${MUTOHPLOT_HEALTH_URL:-http://127.0.0.1:8040/api/status}"

SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$SOURCE_DIR/pyproject.toml")"
if [[ -z "$VERSION" ]]; then
    echo "Keine Version in pyproject.toml gefunden" >&2
    exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_DIR="$RELEASES_DIR/${VERSION}-${STAMP}"
PREVIOUS_TARGET="$(readlink "$CURRENT_LINK" 2>/dev/null || true)"
if [[ -z "$PREVIOUS_TARGET" && -d "$LEGACY_DIR" ]]; then
    PREVIOUS_TARGET="$LEGACY_DIR"
fi

mkdir -p "$RELEASES_DIR" "$BACKUP_DIR"
if [[ -f "$HOME/.config/mutohplot/web-pens.json" ]]; then
    cp "$HOME/.config/mutohplot/web-pens.json" "$BACKUP_DIR/web-pens-${STAMP}.json"
fi
if [[ -f "$HOME/.config/mutohplot/calibration-profiles.json" ]]; then
    cp "$HOME/.config/mutohplot/calibration-profiles.json" \
        "$BACKUP_DIR/calibration-profiles-${STAMP}.json"
fi
if [[ -f "$APP_HOME/jobs.json" ]]; then
    cp "$APP_HOME/jobs.json" "$BACKUP_DIR/jobs-${STAMP}.json"
fi
if [[ -f "$APP_HOME/queue.json" ]]; then
    cp "$APP_HOME/queue.json" "$BACKUP_DIR/queue-${STAMP}.json"
fi

mkdir "$RELEASE_DIR"
cp -R "$SOURCE_DIR"/. "$RELEASE_DIR"/
rm -rf "$RELEASE_DIR/.git" "$RELEASE_DIR/.pytest_cache" "$RELEASE_DIR/.ruff_cache"

python3 -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/pip" install --disable-pip-version-check "$RELEASE_DIR"
"$RELEASE_DIR/.venv/bin/pip" install --disable-pip-version-check pytest
"$RELEASE_DIR/.venv/bin/python" -m pytest -q "$RELEASE_DIR/tests"

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK.new"
mv -Tf "$CURRENT_LINK.new" "$CURRENT_LINK"

rollback() {
    if [[ -n "$PREVIOUS_TARGET" ]]; then
        ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK.new"
        mv -Tf "$CURRENT_LINK.new" "$CURRENT_LINK"
        systemctl --user restart "$SERVICE_NAME" || true
    fi
}
trap rollback ERR

install -m 0644 "$RELEASE_DIR/deploy/mutohplot-web.service" \
    "$HOME/.config/systemd/user/mutohplot-web.service"
systemctl --user daemon-reload
systemctl --user restart "$SERVICE_NAME"

for _ in {1..15}; do
    if curl -fsS --max-time 2 "$HEALTH_URL" | grep -q "\"version\": \"$VERSION\""; then
        trap - ERR
        echo "MutohPlot $VERSION erfolgreich bereitgestellt: $RELEASE_DIR"
        exit 0
    fi
    sleep 1
done

echo "Gesundheitsprüfung für MutohPlot $VERSION fehlgeschlagen" >&2
false
