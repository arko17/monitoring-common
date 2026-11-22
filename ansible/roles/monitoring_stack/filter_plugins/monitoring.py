"""Filters that turn the site inventory into vmagent file_sd target lists."""


def _addr(host, hostvars):
    hv = hostvars[host]
    return hv.get("monitoring_address") or hv.get("ansible_host") or host


def monitoring_target(host, hostvars, port=None):
    """Inventory host -> file_sd entry. instance label = inventory name."""
    addr = _addr(host, hostvars)
    hv = hostvars[host]
    labels = {"instance": host}
    for key in ("role", "location", "owner"):
        if hv.get("monitoring_" + key):
            labels[key] = str(hv["monitoring_" + key])
    return {"targets": [f"{addr}:{port}" if port else addr], "labels": labels}


def physical_hosts(hosts, hostvars, groups):
    """Hosts with physical disks: bare_metal/pve_hosts members or physical: true."""
    implied = set(groups.get("bare_metal", [])) | set(groups.get("pve_hosts", []))
    out = []
    for h in hosts:
        flag = hostvars[h].get("physical")
        if flag is True or (flag is None and h in implied):
            out.append(h)
    return out


def probe_target(probe):
    """service_probes entry -> file_sd entry for the blackbox job."""
    return {
        "targets": [probe["url"]],
        "labels": {"instance": probe["name"], "module": probe.get("module", "http_2xx")},
    }


class FilterModule:
    def filters(self):
        return {
            "monitoring_target": monitoring_target,
            "physical_hosts": physical_hosts,
            "probe_target": probe_target,
        }
