#!/bin/sh
# Local / CI validation for common and a site repo. Needs: ansible-core, yamllint, docker (optional).
#   ./scripts-validate.sh            (in common)
set -eu
cd "$(dirname "$0")"
yamllint -c .yamllint rules ansible
# vmalert can dry-run rule files (no datasource needed)
if command -v docker >/dev/null; then
  docker run --rm -v "$PWD/rules:/rules:ro" victoriametrics/vmalert:v1.156.0 \
    -rule='/rules/*.yml' -dryRun
fi
python3 -m json.tool dashboards/overview.json >/dev/null
echo "common: OK"
