import json
import sys
import html
import re
from datetime import datetime, timezone

old_file = sys.argv[1]
new_file = sys.argv[2]

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

# ── defikarte.ch CI-Farben ─────────────────────────────────────────────────
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


def entry_data(category, feature, changes=None):
    p = props(feature)
    lon, lat = coords(feature)
    key = get_key(feature)
    addr = address(p)
    name = str(p.get("name", "(ohne Name)"))
    link = map_link(lon, lat, key)

    is_247_badge = False
    if category == "Neu" and p.get("opening_hours") == "24/7":
        is_247_badge = True

    change_lines = []
    if changes:
        for label, old_v, new_v in changes:
            gain_247 = (label == "Öffnungszeiten" and str(new_v) == "24/7")
            loss_247 = (label == "Öffnungszeiten" and str(old_v) == "24/7" and str(new_v) != "24/7")
            if gain_247:
                is_247_badge = True
            change_lines.append((label, old_v, new_v, gain_247, loss_247))

    return {
        "category": category, "name": name, "addr": addr, "link": link,
        "change_lines": change_lines, "is_247_badge": is_247_badge,
    }


def status_color(entry):
    return {"Neu": COLOR_NEU, "Geändert": COLOR_GEAENDERT, "Gelöscht": COLOR_GELOESCHT}[entry["category"]]


def dot(color):
    return (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background-color:{color};margin-right:7px;"></span>')


def render_change_lines(change_lines, size=13):
    if not change_lines:
        return ""
    parts = []
    for label, old_v, new_v, gain_247, loss_247 in change_lines:
        if gain_247:
            parts.append(
                f'<div style="font-size:{size}px;margin-top:2px;">'
                f'<span style="color:{GREEN_DARK};font-weight:700;">{html.escape(label)}: neu {html.escape(str(new_v))}</span>'
                f'{badge_247()}</div>'
            )
        elif loss_247:
            parts.append(
                f'<div style="font-size:{size}px;margin-top:2px;">'
                f'<span style="color:{COLOR_GEAENDERT};font-weight:700;">{html.escape(label)}: nicht mehr 24/7 '
                f'({html.escape(str(old_v))} \u2192 {html.escape(str(new_v))})</span></div>'
            )
        else:
            parts.append(
                f'<div style="color:{MUTED};font-size:{size}px;margin-top:2px;">'
                f'{html.escape(label)} {html.escape(str(old_v))} \u2192 {html.escape(str(new_v))}</div>'
            )
    return "".join(parts)


old = load(old_file)
new = load(new_file)
old_idx = index(old.get("features", []) or [])
new_idx = index(new.get("features", []) or [])

added = sorted(set(new_idx) - set(old_idx))
removed = sorted(set(old_idx) - set(new_idx))
common = sorted(set(new_idx) & set(old_idx))

entries = []
for k in added:
    entries.append(entry_data("Neu", new_idx[k]))
for k in removed:
    entries.append(entry_data("Gelöscht", old_idx[k]))
for k in common:
    op, npr = props(old_idx[k]), props(new_idx[k])
    changes = []
    for f in RELEVANT_FIELDS:
        if op.get(f) != npr.get(f):
            changes.append((FIELD_LABELS.get(f, f), op.get(f), npr.get(f)))
    if changes:
        entries.append(entry_data("Geändert", new_idx[k], changes))

if not entries:
    sys.exit(0)

summary = {"Neu": 0, "Geändert": 0, "Gelöscht": 0}
for e in entries:
    summary[e["category"]] += 1

now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y, %H:%M UTC")

legend = f'''
<table role="presentation" style="margin:14px 0 4px 0;">
  <tr style="font-size:13px;color:{MUTED};">
    <td style="padding-right:16px;">{dot(COLOR_NEU)}Neu</td>
    <td style="padding-right:16px;">{dot(COLOR_GEAENDERT)}Geändert</td>
    <td>{dot(COLOR_GELOESCHT)}Gelöscht</td>
  </tr>
</table>
'''

body_html = ""

if len(entries) <= LIST_THRESHOLD:
    lines = []
    for e in entries:
        c = status_color(e)
        addr_part = f'<span style="color:{MUTED};"> · {html.escape(e["addr"])}</span>' if e["addr"] else ""
        name_badge = badge_247() if (e["is_247_badge"] and e["category"] == "Neu") else ""
        changes_html = render_change_lines(e["change_lines"])
        lines.append(f'''
        <table role="presentation" width="100%" style="border-collapse:collapse;">
          <tr>
            <td style="padding:12px 0;border-bottom:1px solid {RULE};">
              <span style="font-size:12px;color:{c};font-weight:600;">{dot(c)}{html.escape(e["category"])}</span><br>
              <span style="font-size:15px;font-weight:600;color:{INK};margin-top:4px;display:inline-block;">{html.escape(e["name"])}</span>{addr_part}{name_badge}
              {changes_html}
              <div style="font-size:13px;margin-top:4px;">{e["link"]}</div>
            </td>
          </tr>
        </table>
        ''')
    body_html = "".join(lines)
else:
    rows = []
    for e in entries:
        c = status_color(e)
        addr_html = f'<div style="color:{MUTED};font-size:12px;">{html.escape(e["addr"])}</div>' if e["addr"] else ""
        name_badge = badge_247() if (e["is_247_badge"] and e["category"] == "Neu") else ""
        changes_html = render_change_lines(e["change_lines"], size=13)
        rows.append(f'''
        <tr>
          <td style="padding:10px 8px 10px 0;border-bottom:1px solid {RULE};white-space:nowrap;">
            <span style="font-size:13px;color:{c};font-weight:600;">{dot(c)}{html.escape(e["category"])}</span>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid {RULE};">
            <span style="font-weight:600;color:{INK};">{html.escape(e["name"])}</span>{name_badge}
            {addr_html}
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid {RULE};">{changes_html}</td>
          <td style="padding:10px 0;border-bottom:1px solid {RULE};font-size:13px;">{e["link"]}</td>
        </tr>
        ''')
    body_html = f'''
    <table role="presentation" width="100%" style="border-collapse:collapse;margin-top:4px;">
      {''.join(rows)}
    </table>
    '''

html_mail = f"""
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
Änderungen an Defibrillatoren im Einzugsgebiet
</h1>

<p style="font-family:{FONT};font-size:13px;color:{MUTED};margin:0;">
Stand {now_str}
</p>

{legend}

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

with open("diff.html", "w", encoding="utf-8") as f:
    f.write(html_mail)
