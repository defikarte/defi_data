import json
import sys
import html
from pathlib import Path

# Kombinierte Bounding Box Schweiz + Liechtenstein (mit kleinem Puffer)
LON_MIN, LON_MAX = 5.9, 10.6
LAT_MIN, LAT_MAX = 45.8, 47.9

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
        return c[0], c[1]  # lon, lat
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

def get_key(feature):
    p = feature.get("properties", {}) or {}
    for k in ("@id", "osm_id", "osm:id", "id", "osmid", "osmId"):
        v = p.get(k)
        if v is not None and str(v).strip():
            s = str(v).strip()
            import re
            if re.match(r"^(node|way|relation)/\d+$", s):
                return s
            if re.match(r"^\d+$", s):
                return f"node/{s}"
            return s
    v = feature.get("id")
    if v is not None and str(v).strip():
        return str(v).strip()
    return None

def maps_links(lon, lat, key=None):
    links = []
    if key and key.startswith(("node/", "way/", "relation/")):
        links.append(f'<a href="https://www.openstreetmap.org/{key}">OSM</a>')
    elif lon is not None and lat is not None:
        links.append(f'<a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}">OSM</a>')
    return " | ".join(links)

def is_valid(lon, lat):
    if lon is None or lat is None:
        return False, "keine Koordinaten"
    if not (LON_MIN <= lon <= LON_MAX):
        return False, f"Longitude {lon} ausserhalb [{LON_MIN}, {LON_MAX}]"
    if not (LAT_MIN <= lat <= LAT_MAX):
        return False, f"Latitude {lat} ausserhalb [{LAT_MIN}, {LAT_MAX}]"
    return True, None

# Dateien aus Argumenten einlesen
files = sys.argv[1:]
if not files:
    print("Keine GeoJSON-Dateien angegeben.")
    sys.exit(0)

invalid_entries = []

for filepath in files:
    source = Path(filepath).name
    try:
        data = load(filepath)
    except Exception as e:
        print(f"Fehler beim Laden von {filepath}: {e}")
        continue

    for feature in data.get("features", []) or []:
        lon, lat = coords(feature)
        valid, reason = is_valid(lon, lat)
        if not valid:
            p = feature.get("properties", {}) or {}
            key = get_key(feature)
            name = p.get("name", "(ohne Name)")
            addr = address(p)
            links = maps_links(lon, lat, key)
            invalid_entries.append({
                "source": source,
                "key": key or "",
                "name": name,
                "address": addr or "",
                "lon": lon,
                "lat": lat,
                "reason": reason,
                "links": links,
            })

if not invalid_entries:
    print("Alle Koordinaten sind plausibel. Kein Report nötig.")
    sys.exit(0)

# HTML-Report generieren
rows = []
for e in invalid_entries:
    coord_str = f"{e['lon']}, {e['lat']}" if e['lon'] is not None else "fehlt"
    rows.append(f"""
    <tr>
      <td>{html.escape(e['source'])}</td>
      <td>{html.escape(e['name'])}<br><small>ID: {html.escape(e['key'])}</small></td>
      <td>{html.escape(e['address'])}</td>
      <td>{html.escape(coord_str)}</td>
      <td>{html.escape(e['reason'])}</td>
      <td>{e['links']}</td>
    </tr>
    """)

report = f"""
<html>
<head>
<meta charset="utf-8"/>
<style>
body {{ font-family: Arial, sans-serif; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
th {{ background-color: #f4f4f4; }}
tr {{ background-color: #ffe6e6; }}
small {{ color: #666; }}
</style>
</head>
<body>
<img src="https://defikarte.ch/defikarte-logo-quer-gruen-positiv-rgb.png" alt="defikarte.ch" style="width:200px;"/>
<h2>⚠️ GeoJSON-Validierung: Verdächtige Koordinaten</h2>
<p>Die folgenden Defi-Einträge haben Koordinaten ausserhalb der erwarteten Bounding Box
(Lon {LON_MIN}–{LON_MAX} / Lat {LAT_MIN}–{LAT_MAX}).</p>
<p><strong>{len(invalid_entries)} verdächtige Einträge gefunden</strong></p>
<table>
  <tr>
    <th>Datei</th>
    <th>Name</th>
    <th>Adresse</th>
    <th>Koordinaten</th>
    <th>Problem</th>
    <th>Karte</th>
  </tr>
  {''.join(rows)}
</table>
<br>
<p>Bitte die betroffenen Einträge in OpenStreetMap prüfen und korrigieren.</p>
<h6>Dies ist eine automatisch generierte E-Mail von defikarte.ch</h6>
</body>
</html>
"""

with open("validation_report.html", "w", encoding="utf-8") as f:
    f.write(report)

print(f"validation_report.html geschrieben: {len(invalid_entries)} verdächtige Einträge.")
