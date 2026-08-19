import json
import sys
import html
import re
import os
from datetime import datetime, timezone

old_file = sys.argv[1]
new_file = sys.argv[2]
pending_file = sys.argv[3] if len(sys.argv) > 3 else ".reporting/pending_changes_be.json"

DEFIKARTE_LOGO_URL = "https://assets.defikarte.ch/logo/logo_gruen.jpg"

RELEVANT_FIELDS = [
    "name", "status", "operator", "phone", "access", "opening_hours",
    "defibrillator:location", "description", "level",
    "addr:street", "addr:housenumber", "addr:postcode", "addr:city", "indoor",
]

def load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def coords(feature):
    try:
        g = feature.get("geometry") or {}
        if g.get("type") != "Point":
            return None, None
        c = g.get("coordinates")
        if not (isinstance(c, list) and len(c) >= 2):
            return None, None
        return c[0], c[1]
    except Exception:
        return None, None

def address(props: dict):
    parts = []
    street = props.get("addr:street")
    housenumber = props.get("addr:housenumber")
    postcode = props.get("addr:postcode")
    city = props.get("addr:city")
    if street or housenumber:
        parts.append(" ".join(p for p in [street, housenumber] if p))
    if postcode or city:
        parts.append(" ".join(p for p in [postcode, city] if p))
    return ", ".join(parts) if parts else None

def normalize_osm_id(s: str) -> str:
    s = str(s).strip()
    if re.match(r"^(node|way|relation)/\d+$", s):
        return s
    if re.match(r"^\d+$", s):
        return f"node/{s}"
    return s

def get_key(feature) -> str | None:
    p = feature.get("properties", {}) or {}
    for k in ("@id", "osm_id", "osm:id", "id", "osmid", "osmId"):
        v = p.get(k)
        if v is not None and str(v).strip():
            return normalize_osm_id(v)
    v = feature.get("id")
    if v is not None and str(v).strip():
        return normalize_osm_id(v)
    lon, lat = coords(feature)
    name = p.get("name", "")
    if lon is not None and lat is not None:
        return f"fallback:{name}:{lon}:{lat}"
    return None

def maps_links(lon, lat, key=None):
    links = []
    if key and key.startswith(("node/", "way/", "relation/")):
        links.append(f'<a href="https://www.openstreetmap.org/{key}">OSM</a>')
    elif lon is not None and lat is not None:
        links.append(f'<a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}">OSM</a>')
    if lon is not None and lat is not None:
        links.append(f'<a href="https://www.google.com/maps?q={lat},{lon}">Google Maps</a>')
    return " | ".join(links)

def index(features):
    out = {}
    for f in features:
        k = get_key(f)
        if k:
            out[k] = f
    return out

def props(feature):
    return feature.get("properties", {}) or {}

def build_row(category, feature, changes=None):
    p = props(feature)
    lon, lat = coords(feature)
    key = get_key(feature)
    addr = address(p)
    links = maps_links(lon, lat, key)
    css = {"neu": "new", "gelöscht": "removed", "geändert": "changed"}[category]
    name = str(p.get("name", "(ohne Name)"))
    return f"""
    <tr class="{css}">
      <td>{html.escape(category)}</td>
      <td>{html.escape(name)}<br><small>ID: {html.escape(key or "")}</small></td>
      <td>{html.escape(addr) if addr else ""}</td>
      <td>{html.escape(f"{lon}, {lat}") if lon is not None and lat is not None else ""}</td>
      <td>{links}</td>
      <td>{("<br>".join(html.escape(c) for c in changes)) if changes else ""}</td>
    </tr>
    """

def build_html(rows, summary):
    return f"""
<html>
<head>
<meta charset="utf-8"/>
<style>
body {{ font-family: Arial, sans-serif; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
th {{ background-color: #f4f4f4; }}
tr.new {{ background-color: #e6ffe6; }}
tr.removed {{ background-color: #ffe6e6; }}
tr.changed {{ background-color: #fff8e6; }}
small {{ color: #666; }}
</style>
</head>
<body>
<img src="{DEFIKARTE_LOGO_URL}" alt="defikarte.ch" style="width:200px;"/>
<h2>Änderungen an Defibrillatoren – Kanton Bern</h2>
<p><strong>Zusammenfassung:</strong> {summary.get('neu', 0)} neu, {summary.get('gelöscht', 0)} gelöscht</p>
<table>
  <tr>
    <th>Status</th><th>Name</th><th>Adresse</th>
    <th>Koordinaten</th><th>Karte</th><th>Details</th>
  </tr>
  {''.join(rows)}
</table>
<br>
<p>Zur Erklärung: Die Tabelle zeigt immer den Status (neu, gelöscht) des Datensatzes an.</p>
<h6>Dies ist eine automatisch generierte E-Mail von defikarte.ch</h6>
</body>
</html>
"""

old = load(old_file)
new = load(new_file)

old_idx = index(old.get("features", []) or [])
new_idx = index(new.get("features", []) or [])

added   = sorted(set(new_idx) - set(old_idx))
removed = sorted(set(old_idx) - set(new_idx))
common  = sorted(set(new_idx) & set(old_idx))

immediate_rows = []
immediate_summary = {"neu": 0, "gelöscht": 0}

for k in added:
    immediate_rows.append(build_row("neu", new_idx[k]))
    immediate_summary["neu"] += 1

for k in removed:
    immediate_rows.append(build_row("gelöscht", old_idx[k]))
    immediate_summary["gelöscht"] += 1

changed_entries = []
for k in common:
    op = props(old_idx[k])
    np = props(new_idx[k])
    changes = []
    for f in RELEVANT_FIELDS:
        if op.get(f) != np.get(f):
            changes.append(f"{f}: '{op.get(f)}' → '{np.get(f)}'")
    if changes:
        lon, lat = coords(new_idx[k])
        changed_entries.append({
            "key": k,
            "name": np.get("name", "(ohne Name)"),
            "address": address(np),
            "lon": lon,
            "lat": lat,
            "changes": changes,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

os.makedirs(os.path.dirname(pending_file), exist_ok=True)
existing = []
if os.path.exists(pending_file):
    try:
        with open(pending_file, encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, ValueError):
        existing = []

existing_by_key = {e["key"]: e for e in existing}
for entry in changed_entries:
    existing_by_key[entry["key"]] = entry

with open(pending_file, "w", encoding="utf-8") as f:
    json.dump(list(existing_by_key.values()), f, ensure_ascii=False, indent=2)

print(f"Pending changes gespeichert: {len(changed_entries)} neu/aktualisiert, "
      f"{len(existing_by_key)} total in {pending_file}")

if immediate_rows:
    with open("diff_immediate.html", "w", encoding="utf-8") as f:
        f.write(build_html(immediate_rows, immediate_summary))
    print(f"diff_immediate.html geschrieben: {immediate_summary}")
else:
    print("Keine sofortigen Änderungen (neu/gelöscht).")
