#!/usr/bin/env python3
"""Prometheus exporter for RCT Power inverters (RCT protocol on TCP 8899).

Reads a fixed set of values on every scrape over a short-lived connection,
so the inverter's Wi-Fi module is not kept busy. Stdlib only + rctclient.
"""
import os
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rctclient.frame import ReceiveFrame, make_frame
from rctclient.registry import REGISTRY as R
from rctclient.types import Command
from rctclient.utils import decode_value

HOST = os.environ.get("RCT_HOST", "")
PORT = int(os.environ.get("RCT_PORT", "8899"))
LISTEN = int(os.environ.get("LISTEN_PORT", "9894"))
LOCK = threading.Lock()

# (rct object, metric name, labels, help, transform)
ABS = abs
GAUGES = [
    ("battery.soc", "rct_battery_soc_ratio", {}, "Battery state of charge (0..1).", None),
    ("battery.soh", "rct_battery_soh_ratio", {}, "Battery state of health (0..1).", None),
    ("power_mng.soc_min", "rct_battery_soc_min_ratio", {}, "Configured minimum state of charge (0..1).", None),
    ("battery.temperature", "rct_battery_temperature_celsius", {}, "Battery temperature.", None),
    ("battery.cycles", "rct_battery_cycles", {}, "Battery charge cycles.", None),
    ("g_sync.p_acc_lp", "rct_battery_power_watts", {}, "Battery power (positive = discharging).", None),
    ("dc_conv.dc_conv_struct[0].p_dc_lp", "rct_pv_power_watts", {"string": "A"}, "PV power per string.", None),
    ("dc_conv.dc_conv_struct[1].p_dc_lp", "rct_pv_power_watts", {"string": "B"}, "PV power per string.", None),
    ("g_sync.p_ac_load_sum_lp", "rct_house_power_watts", {}, "House consumption.", None),
    ("g_sync.p_ac_grid_sum_lp", "rct_grid_power_watts", {}, "Grid power (positive = import, negative = feed-in).", None),
    ("g_sync.p_ac_sum_lp", "rct_inverter_ac_power_watts", {}, "Inverter AC output.", None),
    ("energy.e_dc_day[0]", "rct_pv_energy_today_wh", {"string": "A"}, "PV energy today per string.", None),
    ("energy.e_dc_day[1]", "rct_pv_energy_today_wh", {"string": "B"}, "PV energy today per string.", None),
    ("energy.e_grid_feed_day", "rct_grid_feed_energy_today_wh", {}, "Energy fed into the grid today.", ABS),
    ("energy.e_grid_load_day", "rct_grid_import_energy_today_wh", {}, "Energy imported from the grid today.", ABS),
    ("energy.e_load_day", "rct_house_energy_today_wh", {}, "House consumption today.", None),
    ("prim_sm.state", "rct_inverter_state", {}, "Inverter state machine (RCT prim_sm.state).", None),
    ("db.temp1", "rct_temperature_celsius", {"sensor": "board"}, "Inverter temperatures.", None),
    ("db.core_temp", "rct_temperature_celsius", {"sensor": "core"}, "Inverter temperatures.", None),
]
for i in range(4):
    GAUGES.append((f"fault[{i}].flt", "rct_fault_flags", {"index": str(i)}, "Fault bit fields (0 = no fault).", None))
COUNTERS = [
    ("energy.e_dc_total[0]", "rct_pv_energy_wh_total", {"string": "A"}, "PV energy lifetime per string.", None),
    ("energy.e_dc_total[1]", "rct_pv_energy_wh_total", {"string": "B"}, "PV energy lifetime per string.", None),
    ("energy.e_grid_feed_total", "rct_grid_feed_energy_wh_total", {}, "Energy fed into the grid, lifetime.", ABS),
    ("energy.e_grid_load_total", "rct_grid_import_energy_wh_total", {}, "Energy imported from the grid, lifetime.", ABS),
    ("energy.e_load_total", "rct_house_energy_wh_total", {}, "House consumption, lifetime.", None),
    ("battery.stored_energy", "rct_battery_charged_energy_wh_total", {}, "Energy charged into the battery, lifetime.", None),
    ("battery.used_energy", "rct_battery_discharged_energy_wh_total", {}, "Energy discharged from the battery, lifetime.", None),
]
INFO = [("android_description", "model"), ("inverter_sn", "serial")]


def read_all():
    sock = socket.create_connection((HOST, PORT), timeout=5)
    try:
        def read(name):
            oi = R.get_by_name(name)
            sock.send(make_frame(command=Command.READ, id=oi.object_id))
            frame, deadline = ReceiveFrame(), time.time() + 3
            while time.time() < deadline:
                ready, _, _ = select.select([sock], [], [], 0.5)
                if not ready:
                    continue
                buf = sock.recv(1024)
                if not buf:
                    raise ConnectionError("connection closed")
                while buf:
                    n = frame.consume(buf)
                    buf = buf[n:]
                    if frame.complete():
                        if frame.id == oi.object_id:
                            return decode_value(oi.response_data_type, frame.data)
                        frame = ReceiveFrame()   # unrelated frame, keep reading
            raise TimeoutError(name)
        values = {}
        for name, *_ in GAUGES + COUNTERS:
            values[name] = read(name)
        info = {label: str(read(name)) for name, label in INFO}
        return values, info
    finally:
        sock.close()


def render():
    out, started = [], time.time()
    try:
        with LOCK:
            values, info = read_all()
        up = 1
    except Exception as exc:  # noqa: BLE001 - any failure means "inverter not readable"
        values, info, up = {}, {}, 0
        out.append(f"# scrape error: {type(exc).__name__}: {exc}")
    out += ["# HELP rct_up 1 if the inverter could be read.", "# TYPE rct_up gauge", f"rct_up {up}",
            "# TYPE rct_scrape_duration_seconds gauge", f"rct_scrape_duration_seconds {time.time() - started:.3f}"]
    seen = set()
    for kind, table in (("gauge", GAUGES), ("counter", COUNTERS)):
        for name, metric, labels, help_, fn in table:
            if name not in values:
                continue
            v = float(values[name])
            v = fn(v) if fn else v
            if abs(v) < 1e-6:
                v = 0.0     # the inverter reports denormal floats instead of 0
            if metric not in seen:
                out += [f"# HELP {metric} {help_}", f"# TYPE {metric} {kind}"]
                seen.add(metric)
            lbl = ",".join(f'{k}="{val}"' for k, val in labels.items())
            out.append(f"{metric}{{{lbl}}} {v}" if lbl else f"{metric} {v}")
    if info:
        lbl = ",".join(f'{k}="{v}"' for k, v in info.items())
        out += ["# TYPE rct_info gauge", f"rct_info{{{lbl}}} 1"]
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/metrics"):
            body, code = render().encode(), 200
        else:
            body, code = b"RCT Power exporter: /metrics\n", 200
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not HOST:
        raise SystemExit("RCT_HOST not set")
    ThreadingHTTPServer(("0.0.0.0", LISTEN), Handler).serve_forever()
