#!/bin/sh
# Writes pending APT upgrades per origin and the reboot-required flag
# in Prometheus textfile format. Does not change the system (simulation only).
set -eu
out="${1:?usage: apt-metrics.sh <output.prom>}"
tmp="$out.$$"

{
  echo '# HELP apt_upgrades_pending Pending APT upgrades by origin.'
  echo '# TYPE apt_upgrades_pending gauge'
  apt-get --just-print dist-upgrade 2>/dev/null \
    | awk '/^Inst/ { o=$0; sub(/^[^(]*\([^ ]* /, "", o); sub(/ \[.*$/, "", o); sub(/\)$/, "", o); split(o, a, " "); n[a[1]]++ }
           END { for (k in n) printf "apt_upgrades_pending{origin=\"%s\"} %d\n", k, n[k];
                 if (length(n) == 0) print "apt_upgrades_pending{origin=\"\"} 0" }'
  echo '# HELP node_reboot_required 1 if /var/run/reboot-required exists.'
  echo '# TYPE node_reboot_required gauge'
  if [ -f /var/run/reboot-required ]; then echo 'node_reboot_required 1'; else echo 'node_reboot_required 0'; fi
} > "$tmp"
mv "$tmp" "$out"
