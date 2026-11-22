# monitoring-common

Shared building blocks for Simon's monitoring sites (numerics, SQS, private) and the personal hub.
Included in every site/hub repo as a git submodule at `./common`. Contains **no secrets**.

| Path | Content |
|---|---|
| `ansible/roles/` | `node_exporter`, `smartctl_exporter`, `ipmi_exporter`, `wireguard_metrics`, `beszel_agent`, `docker`, `monitoring_stack` (site stack), `hub_stack` (hub), `automation` (nightly/weekly self-update timers) |
| `ansible/playbooks/site.yml` | shared site playbook, imported by each site repo |
| `rules/` | vmalert alert rules (node, hardware, Proxmox/PBS, probes, meta) |
| `dashboards/` | Grafana dashboards (`overview.json` + pinned community dashboards, `fetch.sh`) |
| `windows/` | Beszel agent install/update scripts for Windows PCs |
| `renovate.json` | Renovate config: bumps pinned image tags and binary versions |

Validate: `./scripts-validate.sh` (yamllint + `vmalert -dryRun`).
