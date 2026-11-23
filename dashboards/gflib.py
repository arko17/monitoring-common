"""Shared Grafana building blocks for the monitoring dashboards (stdlib only).

Design rules: status colors (good/warning/serious/critical) only for state, site
identity in fixed categorical order, history as timelines, current values as
sorted horizontal bars, numbers in text color.
"""
import json
import os

DS = {"type": "prometheus", "uid": "vm"}
S = 'site=~"$site"'

# Status palette (fixed) and categorical slots (fixed order) for the dark theme.
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
SITE_COLORS = {"numerics": "#3987e5", "sqs": "#d95926", "private": "#199e70", "hub": "#c98500"}
NEUTRAL = "text"

NODE_LINK = [{"title": "Host details",
              "url": "/d/rYdddlPWk/node-exporter-full?var-job=node&var-node=${__data.fields.instance}&${__url_time_range}"}]

panels = []
_y = 0
_id = 0


def nid():
    global _id
    _id += 1
    return _id


def row(title):
    global _y
    panels.append({"type": "row", "title": title, "collapsed": False, "id": nid(),
                   "gridPos": {"x": 0, "y": _y, "w": 24, "h": 1}, "panels": []})
    _y += 1


def place(items, h):
    """items: list of (panel, width). Lays them out left to right on one band."""
    global _y
    x = 0
    for p, w in items:
        p["gridPos"] = {"x": x, "y": _y, "w": w, "h": h}
        p["id"] = nid()
        panels.append(p)
        x += w
    _y += h


def thresholds(*steps):
    """steps: (color, from_value) with the first from_value None."""
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}


def target(expr, legend="", instant=False, fmt="time_series", ref="A"):
    return {"refId": ref, "datasource": DS, "expr": expr, "legendFormat": legend,
            "instant": instant, "range": not instant, "format": fmt}


def stat(title, expr, desc, thr, unit="none", color_mode="background", decimals=0, graph=False):
    return {
        "type": "stat", "title": title, "description": desc, "datasource": DS,
        "targets": [target(expr, instant=not graph)],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "thresholds": thr,
                                     "color": {"mode": "thresholds"}, "noValue": "0"}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": color_mode, "graphMode": "area" if graph else "none",
                    "justifyMode": "center", "textMode": "value", "wideLayout": True,
                    "showPercentChange": False, "orientation": "auto"},
    }


def status_stat(title, expr, desc, bad_color):
    return stat(title, expr, desc, thresholds((GOOD, None), (bad_color, 1)))


def neutral_stat(title, expr, desc, unit="none"):
    p = stat(title, expr, desc, thresholds((NEUTRAL, None)), unit=unit, color_mode="none", graph=True)
    p["fieldConfig"]["defaults"]["color"] = {"mode": "fixed", "fixedColor": "#3987e5"}
    return p


def bars(title, expr, legend, desc, unit, thr, minv=0, maxv=1, links=None, decimals=0):
    return {
        "type": "bargauge", "title": title, "description": desc, "datasource": DS,
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": unit, "min": minv, "max": maxv, "decimals": decimals,
                                     "thresholds": thr, "color": {"mode": "thresholds"},
                                     "links": links or []}, "overrides": []},
        "options": {"displayMode": "basic", "orientation": "horizontal", "valueMode": "color",
                    "namePlacement": "left", "showUnfilled": True, "sizing": "manual",
                    "minVizHeight": 14, "maxVizHeight": 20, "minVizWidth": 8,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "legend": {"showLegend": False}},
    }


def timeline(title, expr, legend, desc, thr=None, mappings=None, unit="none"):
    return {
        "type": "state-timeline", "title": title, "description": desc, "datasource": DS,
        "targets": [target(expr, legend)],
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": thr or thresholds((CRITICAL, None)),
                                     "color": {"mode": "thresholds"}, "mappings": mappings or [],
                                     "custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": []},
        "options": {"mergeValues": True, "showValue": "never", "alignValue": "left", "rowHeight": 0.8,
                    "legend": {"showLegend": False}, "tooltip": {"mode": "single", "sort": "none"}},
    }


def table(title, targets, desc, organize, overrides=None, sort=None, no_value="Nothing to report"):
    return {
        "type": "table", "title": title, "description": desc, "datasource": DS, "targets": targets,
        "transformations": [{"id": "merge", "options": {}},
                            {"id": "organize", "options": organize}],
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"},
                                                "filterable": False},
                                     "noValue": no_value},
                        "overrides": overrides or []},
        "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False},
                    "sortBy": sort or []},
    }


def color_text_override(field, mappings):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                           {"id": "mappings", "value": mappings}]}


def link_override(field, links):
    return {"matcher": {"id": "byName", "options": field}, "properties": [{"id": "links", "value": links}]}


def value_map(pairs):
    return [{"type": "value", "options": {k: {"text": t, "color": c, "index": i}
                                          for i, (k, t, c) in enumerate(pairs)}}]




def save(path, uid, title, description, extra=None):
    """Write the dashboard JSON with the collected panels."""
    dash = {"uid": uid, "title": title, "id": None, "version": 1, "tags": ["overview"],
            "timezone": "browser", "schemaVersion": 39, "editable": False, "graphTooltip": 1,
            "refresh": "1m", "time": {"from": "now-24h", "to": "now"}, "description": description,
            "templating": {"list": []}, "links": [], "panels": panels}
    dash.update(extra or {})
    with open(path, "w") as fh:
        json.dump(dash, fh, indent=2)
    print(f"wrote {path}: {len(panels)} panels")
