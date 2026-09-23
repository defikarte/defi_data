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

FIELD_LABELS = {
    "name": "Name", "status": "Status", "operator": "Betreiber", "phone": "Telefon",
    "access": "Zugang", "opening_hours": "Öffnungszeiten",
    "defibrillator:location": "Standortbeschreibung", "description": "Beschreibung",
    "level": "Stockwerk", "addr:street": "Strasse", "addr:housenumber": "Hausnummer",
    "addr:postcode": "PLZ", "addr:city": "Ort", "indoor": "Innenbereich",
}
RELEVANT_FIELDS = list(FIELD_LABELS.keys())
LIST_THRESHOLD = 3

GREEN_LIGHT = "#97C568"
GREEN_DARK  = "#144430"
INK         = "#1F2937"
MUTED       = "#6B7280"
RULE        = "#E5E7EB"
BG          = "#FFFFFF"

COLOR_NEU       = GREEN_LIGHT
COLOR_GEAENDERT = "#E8A33D"
COLOR_GELOESCHT = "#DC2626"

FONT = "'Poppins', Arial, Helvetica, sans-serif"


def load(path):
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


def address(props):
    parts = []
    street, hn = props.get("addr:street"), props.get("addr:housenumber")
    postcode, city = props.get("addr:postcode"), props.get("addr:city")
    if street or hn:
        parts.append(" ".join(p for p in [street, hn] if p))
    if postcode or city:
        parts.append(" ".join(p for p in [postcode, city] if p))
    return ", ".join(parts) if parts else None


SHOW_NO_NAME_HINT = True  # dezenter Hinweis "kein Name in OSM" bei Fallback-Titeln


def truncate(s, n=60):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "\u2026"


def display_name(p, lon, lat):
    """Liefert (titel, hat_eigenen_namen, titel_ist_adresse)."""
    name = str(p.get("name") or "").strip()
    if name:
        return name, True, False
    operator = str(p.get("operator") or "").strip()
    location = str(p.get("defibrillator:location")
                   or p.get("defibrillator:location:de")
                   or p.get("description") or "").strip()
    if operator and location:
        return truncate(f"{operator} \u2013 {location}"), False, False
    if operator:
        return truncate(operator), False, False
    if location:
        return truncate(location), False, False
    addr = address(p)
    if addr:
        return addr, False, True
    if lat is not None and lon is not None:
        return f"Standort {lat:.5f}, {lon:.5f}", False, False
    return "Unbenannter Defi", False, False


def name_hint(has_name):
    if has_name or not SHOW_NO_NAME_HINT:
        return ""
    return (f'<span style="color:{MUTED};font-size:12px;font-weight:400;"> '
            f'(kein Name in OSM)</span>')


def get_key(feature):
    p = feature.get("properties", {}) or {}
    for k in ("@id", "osm_id", "osm:id", "id", "osmid", "osmId"):
        v = p.get(k)
        if v is not None and str(v).strip():
            s = str(v).strip()
            if re.match(r"^(node|way|relation)/\d+$", s):
                return s
            if re.match(r"^\d+$", s):
                return f"node/{s}"
            return s
    v = feature.get("id")
    if v is not None and str(v).strip():
        return str(v).strip()
    return None


def map_link(lon, lat, key=None):
    if key and key.startswith(("node/", "way/", "relation/")):
        return f'<a href="https://www.openstreetmap.org/{key}" style="color:{GREEN_DARK};">Karte</a>'
    if lon is not None and lat is not None:
        return f'<a href="https://www.google.com/maps?q={lat},{lon}" style="color:{GREEN_DARK};">Karte</a>'
    return ""


def index(features):
    out = {}
    for f in features:
        k = get_key(f)
        if k:
            out[k] = f
    return out


def props(feature):
    return feature.get("properties", {}) or {}


def badge_247():
    return (f'<span style="display:inline-block;background-color:{GREEN_DARK};color:#ffffff;'
            f'font-size:10px;font-weight:700;letter-spacing:0.3px;padding:2px 7px;'
            f'border-radius:3px;margin-left:8px;vertical-align:middle;">24/7</span>')


def dot(color):
    return (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background-color:{color};margin-right:7px;"></span>')


def html_shell(title, legend_html, body_html, now_str):
    return f"""
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background-color:#F9FAFB;font-family:{FONT};">
<table role="presentation" width="100%" style="background-color:#F9FAFB;border-collapse:collapse;">
<tr><td align="center">
<table role="presentation" width="600" style="max-width:600px;background-color:{BG};border-collapse:collapse;">
<tr><td style="padding:32px 28px;">

<img src="{DEFIKARTE_LOGO_URL}" alt="defikarte.ch" style="height:34px;"/>

<h1 style="font-family:{FONT};font-weight:700;font-size:20px;line-height:1.35;color:{GREEN_DARK};margin:24px 0 6px 0;">
{title}
</h1>

<p style="font-family:{FONT};font-size:13px;color:{MUTED};margin:0;">
Stand {now_str}
</p>

{legend_html}

<div style="font-family:{FONT};margin-top:8px;">
{body_html}
</div>

<p style="font-family:{FONT};font-size:11px;color:{MUTED};margin-top:32px;padding-top:14px;border-top:1px solid {RULE};">
Automatisch generiert von defikarte.ch
</p>

</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


old = load(old_file)
new = load(new_file)
old_idx = index(old.get("features", []) or [])
new_idx = index(new.get("features", []) or [])

added = sorted(set(new_idx) - set(old_idx))
removed = sorted(set(old_idx) - set(new_idx))
common = sorted(set(new_idx) & set(old_idx))

# ── Sofort: Neu + Gelöscht ──────────────────────────────────────────────────
immediate_entries = []

for k in added:
    p = props(new_idx[k])
    lon, lat = coords(new_idx[k])
    key = get_key(new_idx[k])
    dname, has_name, name_is_addr = display_name(p, lon, lat)
    is_247 = p.get("opening_hours") == "24/7"
    immediate_entries.append({
        "category": "Neu", "name": dname,
        "addr": None if name_is_addr else address(p), "link": map_link(lon, lat, key),
        "is_247_badge": is_247, "hint": name_hint(has_name),
    })

for k in removed:
    p = props(old_idx[k])
    lon, lat = coords(old_idx[k])
    key = get_key(old_idx[k])
    dname, has_name, name_is_addr = display_name(p, lon, lat)
    immediate_entries.append({
        "category": "Gelöscht", "name": dname,
        "addr": None if name_is_addr else address(p), "link": map_link(lon, lat, key),
        "is_247_badge": False, "hint": name_hint(has_name),
    })

# ── Geändert: strukturiert in pending-Datei sammeln (für Weekly-Report) ─────
changed_entries = []
for k in common:
    op, npr = props(old_idx[k]), props(new_idx[k])
    changes = []
    for f in RELEVANT_FIELDS:
        if op.get(f) != npr.get(f):
            changes.append({
                "label": FIELD_LABELS.get(f, f),
                "old": op.get(f),
                "new": npr.get(f),
            })
    if changes:
        lon, lat = coords(new_idx[k])
        dname, has_name, name_is_addr = display_name(npr, lon, lat)
        changed_entries.append({
            "key": k,
            "name": dname,
            "has_name": has_name,
            "address": None if name_is_addr else address(npr),
            "lon": lon,
            "lat": lat,
            "changes": changes,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

os.makedirs(os.path.dirname(pending_file) or ".", exist_ok=True)
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

# ── Sofort-Mail HTML schreiben (nur wenn neu/gelöscht vorhanden) ───────────
if immediate_entries:
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y, %H:%M UTC")

    legend = f'''
    <table role="presentation" style="margin:14px 0 4px 0;">
      <tr style="font-size:13px;color:{MUTED};">
        <td style="padding-right:16px;">{dot(COLOR_NEU)}Neu</td>
        <td>{dot(COLOR_GELOESCHT)}Gelöscht</td>
      </tr>
    </table>
    '''

    lines = []
    for e in immediate_entries:
        c = COLOR_NEU if e["category"] == "Neu" else COLOR_GELOESCHT
        addr_part = f'<span style="color:{MUTED};"> · {html.escape(e["addr"])}</span>' if e["addr"] else ""
        name_badge = badge_247() if e["is_247_badge"] else ""
        lines.append(f'''
        <table role="presentation" width="100%" style="border-collapse:collapse;">
          <tr>
            <td style="padding:12px 0;border-bottom:1px solid {RULE};">
              <span style="font-size:12px;color:{c};font-weight:600;">{dot(c)}{html.escape(e["category"])}</span><br>
              <span style="font-size:15px;font-weight:600;color:{INK};margin-top:4px;display:inline-block;">{html.escape(e["name"])}</span>{e["hint"]}{addr_part}{name_badge}
              <div style="font-size:13px;margin-top:4px;">{e["link"]}</div>
            </td>
          </tr>
        </table>
        ''')
    body_html = "".join(lines)

    html_mail = html_shell(
        "Neue und gelöschte Defis – Kanton Bern", legend, body_html, now_str
    )
    with open("diff_immediate.html", "w", encoding="utf-8") as f:
        f.write(html_mail)
    print(f"diff_immediate.html geschrieben: {len(immediate_entries)} Einträge")
else:
    print("Keine sofortigen Änderungen (neu/gelöscht).")
