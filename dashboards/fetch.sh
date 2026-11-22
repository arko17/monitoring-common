#!/bin/sh
# Download pinned community dashboards from grafana.com and bind them to the
# provisioned datasource (uid "vm"). Re-run after changing a revision; commit the JSON.
set -eu
cd "$(dirname "$0")"
# id:revision:file
for d in \
  1860:46:node-exporter-full.json \
  10347:5:proxmox-pve-exporter.json \
  7587:3:blackbox-exporter.json \
  12683:43:vmagent.json
do
  id=${d%%:*}; rest=${d#*:}; rev=${rest%%:*}; file=${rest#*:}
  if [ "$rev" = latest ]; then url="https://grafana.com/api/dashboards/$id/revisions/latest/download"
  else url="https://grafana.com/api/dashboards/$id/revisions/$rev/download"; fi
  echo "fetching $id rev $rev → $file"
  curl -fsSL "$url" \
    | python3 -c '
import json, re, sys
d = json.load(sys.stdin)
d.pop("__inputs", None); d.pop("__requires", None); d["id"] = None
s = json.dumps(d, indent=2)
s = re.sub(r"\$\{DS_[A-Za-z0-9_-]+\}", "vm", s)
print(s)' > "$file"
done
