#!/bin/sh
# Latest handshake and transfer per WireGuard peer, as node_exporter textfile metrics.
set -eu
out="${1:?usage: wg-metrics.sh <output.prom>}"
tmp="$out.$$"
{
  echo '# TYPE wireguard_latest_handshake_seconds gauge'
  wg show all latest-handshakes | awk '{printf "wireguard_latest_handshake_seconds{interface=\"%s\",public_key=\"%s\"} %s\n",$1,$2,$3}'
  echo '# TYPE wireguard_received_bytes_total counter'
  wg show all transfer | awk '{printf "wireguard_received_bytes_total{interface=\"%s\",public_key=\"%s\"} %s\n",$1,$2,$3}'
  echo '# TYPE wireguard_sent_bytes_total counter'
  wg show all transfer | awk '{printf "wireguard_sent_bytes_total{interface=\"%s\",public_key=\"%s\"} %s\n",$1,$2,$4}'
} > "$tmp"
mv "$tmp" "$out"
