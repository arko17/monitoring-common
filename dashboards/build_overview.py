#!/usr/bin/env python3
"""Generates overview.json ("Global overview"). Edit here, run, commit both files.

    python3 build_overview.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gflib import *  # noqa: E402,F401,F403

# ---------------------------------------------------------------------------
# 1. Key figures
# ---------------------------------------------------------------------------
row("Right now")
place([
    (status_stat("Critical alerts",
                 f'count(ALERTS{{alertstate="firing", severity="critical", {S}}}) or vector(0)',
                 "Firing critical alerts (includes silenced ones, which do not notify).", CRITICAL), 4),
    (status_stat("Warnings",
                 f'count(ALERTS{{alertstate="firing", severity="warning", {S}}}) or vector(0)',
                 "Firing warnings.", WARNING), 4),
    (status_stat("Targets down",
                 f'count(up{{{S}}} == 0) or vector(0)',
                 "Scrape targets that do not answer (exporters, stack components).", CRITICAL), 4),
    (status_stat("Outside checks failing",
                 'count(gatus_results_endpoint_success{group=~"$site"} == 0) or vector(0)',
                 "Gatus checks from the internet that currently fail.", SERIOUS), 4),
    (neutral_stat("Hosts reporting",
                  f'count(up{{job="node", {S}}} == 1)',
                  "Servers whose node_exporter answers."), 4),
    (neutral_stat("Workstations online",
                  f'sum(probe_success{{job="blackbox-workstations", {S}}})',
                  "Workstations answering ping right now."), 4),
], h=4)

place([
    (timeline("Site health: share of targets up",
              f'sum by (site) (up{{{S}}}) / count by (site) (up{{{S}}})', "{{site}}",
              "Per site: fraction of scrape targets answering. Green = all, yellow = some down, red = 10 % or more down. "
              "A gap means the site sent no data (see SiteSilent).",
              thr=thresholds((CRITICAL, None), (WARNING, 0.9), (GOOD, 1)), unit="percentunit"), 24),
], h=5)

# ---------------------------------------------------------------------------
# 2. Needs attention
# ---------------------------------------------------------------------------
row("Needs attention")
sev_map = value_map([("critical", "● critical", CRITICAL), ("warning", "● warning", WARNING)])
place([
    (table("Firing alerts",
           [target(f'ALERTS{{alertstate="firing", severity=~"critical|warning", {S}}}', instant=True, fmt="table")],
           "Critical and warning alerts of all sites. Silenced alerts are listed too; info alerts are omitted.",
           {"excludeByName": {"Time": True, "Value": True, "__name__": True, "alertstate": True,
                              "alertgroup": True, "job": True, "temperature_type": True, "attribute_name": True,
                              "attribute_value_type": True, "namespace": True, "storage": True, "plugintype": True},
            "indexByName": {"severity": 0, "site": 1, "alertname": 2, "instance": 3},
            "renameByName": {"severity": "Severity", "site": "Site", "alertname": "Alert", "instance": "Host",
                             "device": "Device", "id": "Guest / storage", "mountpoint": "Mount"}},
           overrides=[color_text_override("Severity", sev_map), link_override("Host", NODE_LINK)],
           sort=[{"displayName": "Severity", "desc": False}],
           no_value="No alerts firing"), 14),
    (table("Down right now",
           [target(f'(up{{{S}}} == 0) or (probe_success{{job="blackbox-services", {S}}} == 0) '
                   'or label_replace(label_replace(label_replace(gatus_results_endpoint_success{group=~"$site"} == 0, '
                   '"instance", "$1", "name", "(.*)"), "site", "$1", "group", "(.*)"), "job", "outside check", "job", ".*")',
                   instant=True, fmt="table")],
           "Scrape targets, internal service checks and outside checks that fail right now.",
           {"excludeByName": {"Time": True, "Value": True, "__name__": True, "module": True, "key": True,
                              "group": True, "name": True, "type": True},
            "indexByName": {"site": 0, "job": 1, "instance": 2},
            "renameByName": {"site": "Site", "job": "Kind", "instance": "Target"}},
           no_value="Everything is up"), 10),
], h=8)

# ---------------------------------------------------------------------------
# 3. Capacity
# ---------------------------------------------------------------------------
row("Capacity (top 10, now)")
use_thr = thresholds((GOOD, None), (WARNING, 0.8), (CRITICAL, 0.95))
place([
    (bars("CPU busy",
          f'sort_desc(topk(10, 1 - avg by (site, instance) (rate(node_cpu_seconds_total{{mode="idle", {S}}}[5m]))))',
          "{{instance}}", "Average CPU utilisation over the last 5 minutes.", "percentunit", use_thr, links=NODE_LINK), 8),
    (bars("Memory used",
          f'sort_desc(topk(10, 1 - node_memory_MemAvailable_bytes{{{S}}} / node_memory_MemTotal_bytes{{{S}}}))',
          "{{instance}}", "RAM in use (MemAvailable based, page cache counts as free).", "percentunit", use_thr,
          links=NODE_LINK), 8),
    (bars("Fullest filesystems",
          f'sort_desc(topk(10, 1 - node_filesystem_avail_bytes{{fstype!~"tmpfs|ramfs|squashfs|overlay|nsfs|vfat|fuse.*", {S}}} '
          f'/ node_filesystem_size_bytes{{fstype!~"tmpfs|ramfs|squashfs|overlay|nsfs|vfat|fuse.*", {S}}}))',
          "{{instance}} {{mountpoint}}", "Used share of host filesystems. Alert at 90 %.", "percentunit",
          thresholds((GOOD, None), (WARNING, 0.8), (CRITICAL, 0.9)), links=NODE_LINK), 8),
], h=9)

# ---------------------------------------------------------------------------
# 4. Software updates
# ---------------------------------------------------------------------------
row("Software updates")
place([
    (status_stat("Hosts with security updates",
                 f'count(sum by (site, instance) (apt_upgrades_pending{{origin=~".*[Ss]ecurity.*", {S}}}) > 0) or vector(0)',
                 "Hosts with pending security updates (unattended-upgrades usually installs them within a day).", WARNING), 8),
    (status_stat("Hosts needing a reboot", f'count(node_reboot_required{{{S}}} == 1) or vector(0)',
                 "Kernel or library updates installed but not active until a reboot.", WARNING), 8),
    (neutral_stat("Updates pending (all hosts)", f'sum(apt_upgrades_pending{{{S}}}) or vector(0)',
                  "Total number of pending package updates over all Debian/Ubuntu/Proxmox hosts."), 8),
], h=4)
UPD = f'apt_upgrades_pending{{{S}}}'
place([
    (table("Updates per host",
           [target(f'sum by (site, instance) ({UPD})', instant=True, fmt="table", ref="A"),
            target(f'sum by (site, instance) (apt_upgrades_pending{{origin=~".*[Ss]ecurity.*", {S}}}) '
                   f'or (sum by (site, instance) ({UPD}) * 0)', instant=True, fmt="table", ref="B"),
            target(f'max by (site, instance) (node_reboot_required{{{S}}})', instant=True, fmt="table", ref="C")],
           "Pending APT updates per host (refreshed hourly on the host), the security share, and whether a reboot is pending.",
           {"excludeByName": {"Time": True},
            "indexByName": {"site": 0, "instance": 1, "Value #B": 2, "Value #A": 3, "Value #C": 4},
            "renameByName": {"site": "Site", "instance": "Host", "Value #A": "Updates pending",
                             "Value #B": "Security updates", "Value #C": "Reboot needed"}},
           overrides=[
               {"matcher": {"id": "byName", "options": "Security updates"},
                "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                               {"id": "thresholds", "value": thresholds((GOOD, None), (WARNING, 1))},
                               {"id": "color", "value": {"mode": "thresholds"}}]},
               {"matcher": {"id": "byName", "options": "Updates pending"},
                "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                               {"id": "thresholds", "value": thresholds((GOOD, None), ("text", 1))},
                               {"id": "color", "value": {"mode": "thresholds"}}]},
               color_text_override("Reboot needed", value_map([("0", "no", GOOD), ("1", "● yes", WARNING)])),
               link_override("Host", NODE_LINK)],
           sort=[{"displayName": "Security updates", "desc": True}],
           no_value="No update data"), 24),
], h=9)

# ---------------------------------------------------------------------------
# 5. Hardware & maintenance
# ---------------------------------------------------------------------------
row("Hardware & maintenance")
place([
    (status_stat("Disks with SMART errors",
                 f'count(smartctl_device_smart_status{{{S}}} == 0) or vector(0)',
                 "Disks reporting SMART failure (includes silenced ones).", CRITICAL), 6),
    (status_stat("RAID / ZFS / NAS degraded",
                 f'(count(node_zfs_zpool_state{{state!="online", {S}}} > 0) or vector(0)) '
                 f'+ (count(raidStatus{{{S}}} != 1) or vector(0)) '
                 f'+ (count(node_md_disks{{state="failed", {S}}} > 0) or vector(0))',
                 "Degraded ZFS pools, Synology volumes and md RAIDs.", CRITICAL), 6),
    (stat("Hottest disk", f'max(smartctl_device_temperature{{temperature_type="current", {S}}})',
          "Highest current drive temperature.", thresholds((GOOD, None), (WARNING, 50), (CRITICAL, 60)),
          unit="celsius", color_mode="value"), 6),
    (stat("Oldest automation run", f'max(time() - monitoring_job_last_success_timestamp_seconds{{{S}}})',
          "Time since the oldest successful nightly/weekly self-update job. Alert after 8 days.",
          thresholds((GOOD, None), (WARNING, 2 * 86400), (CRITICAL, 8 * 86400)), unit="dtdurations",
          color_mode="value"), 6),
], h=4)
place([
    (bars("Drive temperatures (hottest 10)",
          f'sort_desc(topk(10, smartctl_device_temperature{{temperature_type="current", {S}}}))',
          "{{instance}} {{device}}", "Current SMART temperature per drive.", "celsius",
          thresholds((GOOD, None), (WARNING, 50), (CRITICAL, 60)), minv=20, maxv=70, links=NODE_LINK), 12),
    (bars("Certificates: days left",
          f'sort(label_replace((probe_ssl_earliest_cert_expiry{{{S}}} - time()) / 86400, "name", "$1", "instance", "(.*)") '
          'or gatus_results_certificate_expiration_seconds{group=~"$site"} / 86400)',
          "{{name}}", "TLS certificates checked from inside (blackbox) and from the internet (Gatus). Alert below 14 days.",
          "none", thresholds((CRITICAL, None), (WARNING, 14), (GOOD, 30)), minv=0, maxv=400), 12),
], h=8)

# ---------------------------------------------------------------------------
# 6. Outside checks
# ---------------------------------------------------------------------------
row("Outside checks (Gatus, from the internet)")
place([
    (timeline("Availability from the internet",
              'gatus_results_endpoint_success{group=~"$site"}', "{{group}} · {{name}}",
              "History of every Gatus check. Red stripes are outages as seen from outside. "
              "na.uni-tuebingen.de is red on purpose while the university blocks inbound traffic.",
              thr=thresholds((CRITICAL, None), (GOOD, 1)),
              mappings=value_map([("1", "up", GOOD), ("0", "down", CRITICAL)])), 24),
], h=10)

# ---------------------------------------------------------------------------
# 7. Workstations
# ---------------------------------------------------------------------------
row("Workstations")
ws = {
    "type": "timeseries", "title": "Workstations online", "datasource": DS,
    "description": "Number of workstations answering ping, per site.",
    "targets": [target(f'sum by (site) (probe_success{{job="blackbox-workstations", {S}}})', "{{site}}")],
    "fieldConfig": {"defaults": {"unit": "none", "decimals": 0, "min": 0,
                                 "color": {"mode": "fixed", "fixedColor": SITE_COLORS["numerics"]},
                                 "custom": {"drawStyle": "line", "lineInterpolation": "stepAfter", "lineWidth": 2,
                                            "fillOpacity": 12, "gradientMode": "none", "showPoints": "never",
                                            "axisSoftMax": 5, "spanNulls": True}},
                    "overrides": [{"matcher": {"id": "byName", "options": s},
                                   "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                                  for s, c in SITE_COLORS.items()]},
    "options": {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                "tooltip": {"mode": "multi", "sort": "desc"}},
}
place([
    (ws, 14),
    (table("Not seen in the selected period",
           [target(f'label_replace(max_over_time(probe_success{{job="blackbox-workstations", {S}}}[$__range]) == 0, '
                   '"host", "$1", "instance", "([^.]+).*")', instant=True, fmt="table")],
           "Workstations that never answered during the selected time range (switched off, no DNS entry).",
           {"excludeByName": {"Time": True, "Value": True, "__name__": True, "job": True, "instance": True},
            "indexByName": {"site": 0, "host": 1},
            "renameByName": {"site": "Site", "host": "Workstation"}},
           sort=[{"displayName": "Workstation", "desc": False}],
           no_value="All workstations were online"), 10),
], h=8)

save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "overview.json"),
     "global-overview", "Global overview",
     "All sites at a glance. Generated by common/dashboards/build_overview.py.",
     extra={
         "version": 3,
         "templating": {"list": [{
             "name": "site", "label": "Site", "type": "query", "datasource": DS,
             "query": {"query": "label_values(up, site)", "refId": "site"}, "definition": "label_values(up, site)",
             "multi": True, "includeAll": True, "allValue": ".*", "refresh": 2, "sort": 1,
             "current": {"text": "All", "value": "$__all"}}]},
         "links": [
             {"title": "Home", "type": "link", "icon": "dashboard", "url": "/d/home-private"},
             {"title": "Host details", "type": "link", "icon": "dashboard", "url": "/d/rYdddlPWk/node-exporter-full"},
             {"title": "Proxmox", "type": "link", "icon": "dashboard", "url": "/d/Dp7Cd57Zza"},
             {"title": "Status page", "type": "link", "icon": "external link", "url": "https://status.skscience.net",
              "targetBlank": True}],
     })
