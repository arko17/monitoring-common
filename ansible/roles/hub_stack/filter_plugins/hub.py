"""Re-scope the common alert rules to one relay site (evaluated on the hub)."""
import os

import yaml

try:  # keep {{ $labels }} in annotations away from Ansible templating
    from ansible.utils.unsafe_proxy import wrap_var
except ImportError:  # pragma: no cover
    def wrap_var(v):
        return v


def site_rules(path, site, keep_watchdog=False):
    """Load a common rules file and return YAML text where every group
    - is renamed to <site>-<group>,
    - only sees series with site=<site> (vmalert group param extra_label),
    - drops the Watchdog rule unless keep_watchdog (only the hub's own copy keeps it)."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    groups = []
    for g in doc.get("groups", []):
        g = dict(g)
        g["name"] = f"{site}-{g['name']}"
        g["params"] = {"extra_label": [f"site={site}"]}
        g["rules"] = [r for r in g.get("rules", []) if keep_watchdog or r.get("alert") != "Watchdog"]
        if g["rules"]:
            groups.append(g)
    header = f"# Generated from {os.path.basename(path)} for site={site}. Do not edit.\n"
    return wrap_var(header + yaml.safe_dump({"groups": groups}, sort_keys=False, allow_unicode=True, width=200))


class FilterModule:
    def filters(self):
        return {"site_rules": site_rules}
