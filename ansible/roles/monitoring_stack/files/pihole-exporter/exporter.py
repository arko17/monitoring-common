#!/usr/bin/env python3
"""Prometheus exporter for Pi-hole v6 (REST API). Stdlib only.

Keeps one API session and reuses it (Pi-hole limits concurrent sessions);
logs in again only when the session is rejected.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

URL = os.environ.get("PIHOLE_URL", "").rstrip("/") + "/api"
PW_FILE = os.environ.get("PIHOLE_PASSWORD_FILE", "/run/secrets/pihole-password")
LISTEN = int(os.environ.get("LISTEN_PORT", "9617"))
LOCK = threading.Lock()
SID = {"sid": None}


def _password():
    with open(PW_FILE) as fh:
        return fh.read().strip()


def _call(path, body=None, method=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json",
                                          **({"X-FTL-SID": SID["sid"]} if SID["sid"] else {})})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def _login():
    SID["sid"] = None
    SID["sid"] = _call("/auth", {"password": _password()})["session"]["sid"]


def get(path):
    if not SID["sid"]:
        _login()
    try:
        return _call(path)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            _login()
            return _call(path)
        raise


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def render():
    out, started = [], time.time()
    try:
        with LOCK:
            sm = get("/stats/summary")
            blocking = get("/dns/blocking").get("blocking")
            ups = get("/stats/upstreams").get("upstreams", [])
            ver = get("/info/version").get("version", {})
        up = 1
    except Exception as exc:  # noqa: BLE001
        up = 0
        out.append(f"# scrape error: {type(exc).__name__}: {exc}")
    out += ["# HELP pihole_up 1 if the Pi-hole API could be read.", "# TYPE pihole_up gauge", f"pihole_up {up}",
            "# TYPE pihole_scrape_duration_seconds gauge",
            f"pihole_scrape_duration_seconds {time.time() - started:.3f}"]
    if not up:
        return "\n".join(out) + "\n"
    q = sm.get("queries", {})
    out += ["# HELP pihole_queries_24h DNS queries in the last 24 hours by outcome.",
            "# TYPE pihole_queries_24h gauge"]
    for k in ("total", "blocked", "forwarded", "cached"):
        out.append(f'pihole_queries_24h{{status="{k}"}} {q.get(k, 0)}')
    out += ["# TYPE pihole_blocked_ratio gauge", f"pihole_blocked_ratio {q.get('percent_blocked', 0) / 100}",
            "# TYPE pihole_unique_domains_24h gauge", f"pihole_unique_domains_24h {q.get('unique_domains', 0)}",
            "# TYPE pihole_query_frequency gauge", f"pihole_query_frequency {q.get('frequency', 0)}"]
    for t, n in (q.get("types") or {}).items():
        out.append(f'pihole_queries_by_type_24h{{type="{esc(t)}"}} {n}')
    c = sm.get("clients", {})
    out += ["# TYPE pihole_clients gauge", f'pihole_clients{{state="active"}} {c.get("active", 0)}',
            f'pihole_clients{{state="total"}} {c.get("total", 0)}',
            "# TYPE pihole_gravity_domains gauge",
            f"pihole_gravity_domains {sm.get('gravity', {}).get('domains_being_blocked', 0)}",
            "# TYPE pihole_gravity_last_update_timestamp_seconds gauge",
            f"pihole_gravity_last_update_timestamp_seconds {sm.get('gravity', {}).get('last_update', 0)}",
            "# TYPE pihole_blocking_enabled gauge", f"pihole_blocking_enabled {1 if blocking == 'enabled' else 0}",
            "# HELP pihole_upstream_queries_24h Queries answered per upstream / source (24 h).",
            "# TYPE pihole_upstream_queries_24h gauge"]
    for u in ups:   # name alone is not unique (same resolver via IPv4 and IPv6)
        addr = f'{u.get("ip") or ""}#{u.get("port") or ""}'.strip("#")
        out.append(f'pihole_upstream_queries_24h{{upstream="{esc(u.get("name") or u.get("ip"))}",address="{esc(addr)}"}} '
                   f'{u.get("count", 0)}')
    out += ["# HELP pihole_update_available 1 if a newer version is available for the component.",
            "# TYPE pihole_update_available gauge"]
    for comp in ("core", "web", "ftl"):
        loc = (ver.get(comp) or {}).get("local", {}).get("version")
        rem = (ver.get(comp) or {}).get("remote", {}).get("version")
        if loc:
            out.append(f'pihole_update_available{{component="{comp}",local="{esc(loc)}",remote="{esc(rem or "")}"}} '
                       f'{1 if rem and rem != loc else 0}')
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = (render() if self.path.startswith("/metrics") else "Pi-hole exporter: /metrics\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not URL.startswith("http"):
        raise SystemExit("PIHOLE_URL not set")
    ThreadingHTTPServer(("0.0.0.0", LISTEN), Handler).serve_forever()
