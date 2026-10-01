"""
Gemeinsame Bausteine für alle Report-Mails (geojson_diff.py,
geojson_diff_be.py, build_weekly_report.py).

Design-Änderungen (Farben, Karten, Seitenrahmen) nur hier vornehmen.
"""

import html
import re

# ── defikarte.ch CI ──────────────────────────────────────────────────────────
LOGO_URL = "https://assets.defikarte.ch/logo/logo_gruen.jpg"
GREEN_LIGHT = "#97C568"
GREEN_DARK = "#144430"
INK = "#1F2937"
MUTED = "#6B7280"
RULE = "#E5E7EB"
PAGE_BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
CHANGE_BG = "#F9FAFB"
FONT = "'Poppins', Arial, Helvetica, sans-serif"

COLOR_NEU = GREEN_LIGHT
COLOR_GEAENDERT = "#E8A33D"
COLOR_GELOESCHT = "#DC2626"
STATUS_COLORS = {"Neu": COLOR_NEU, "Geändert": COLOR_GEAENDERT, "Gelöscht": COLOR_GELOESCHT}

SHOW_NO_NAME_HINT = True  # "(kein Name in OSM)" bei Einträgen ohne name-Tag

FIELD_LABELS = {
    "name": "Name", "status": "Status", "operator": "Betreiber", "phone": "Telefon",
    "access": "Zugang", "opening_hours": "Öffnungszeiten",
    "defibrillator:location": "Standortbeschreibung", "description": "Beschreibung",
    "level": "Stockwerk", "addr:street": "Strasse", "addr:housenumber": "Hausnummer",
    "addr:postcode": "PLZ", "addr:city": "Ort", "indoor": "Innenbereich",
}
RELEVANT_FIELDS = list(FIELD_LABELS.keys())
OPENING_LABEL = FIELD_LABELS["opening_hours"]


# ── GeoJSON-Hilfsfunktionen ──────────────────────────────────────────────────
def props(feature):
    return feature.get("properties", {}) or {}


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


def address(p):
    parts = []
    street, hn = p.get("addr:street"), p.get("addr:housenumber")
    postcode, city = p.get("addr:postcode"), p.get("addr:city")
    if street or hn:
        parts.append(" ".join(x for x in [street, hn] if x))
    if postcode or city:
        parts.append(" ".join(x for x in [postcode, city] if x))
    return ", ".join(parts) if parts else None


def get_key(feature):
    p = props(feature)
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
    lon, lat = coords(feature)
    if lon is not None and lat is not None:
        return f"fallback:{p.get('name', '')}:{lon}:{lat}"
    return None


def index(features):
    out = {}
    for f in features:
        k = get_key(f)
        if k:
            out[k] = f
    return out


def map_url(lon, lat, key=None):
    if key and key.startswith(("node/", "way/", "relation/")):
        return f"https://www.openstreetmap.org/{key}"
    if lon is not None and lat is not None:
        return f"https://www.google.com/maps?q={lat},{lon}"
    return None


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


def feature_entry(status, feature, changes=None):
    """Baut aus einem GeoJSON-Feature einen Karten-Eintrag."""
    p = props(feature)
    lon, lat = coords(feature)
    name, has_name, name_is_addr = display_name(p, lon, lat)
    return {
        "status": status,
        "name": name,
        "has_name": has_name,
        "addr": None if name_is_addr else address(p),
        "url": map_url(lon, lat, get_key(feature)),
        "new_247": status == "Neu" and p.get("opening_hours") == "24/7",
        "changes": changes or [],
    }


def compute_changes(old_p, new_p):
    """Liste von (label, alt, neu) für alle relevanten geänderten Felder."""
    return [(FIELD_LABELS[f], old_p.get(f), new_p.get(f))
            for f in RELEVANT_FIELDS if old_p.get(f) != new_p.get(f)]


# ── 24/7-Logik ───────────────────────────────────────────────────────────────
def is_gain_247(label, old, new):
    return label == OPENING_LABEL and str(new) == "24/7" and str(old) != "24/7"


def is_loss_247(label, old, new):
    return label == OPENING_LABEL and str(old) == "24/7" and str(new) != "24/7"


def count_247(entries):
    gains = sum(1 for e in entries
                if e.get("new_247") or any(is_gain_247(*c) for c in e["changes"] if len(c) == 3))
    losses = sum(1 for e in entries
                 if any(is_loss_247(*c) for c in e["changes"] if len(c) == 3))
    return gains, losses


# ── Rendering ────────────────────────────────────────────────────────────────
def _e(s):
    return html.escape(str(s))


def val(v):
    return "(leer)" if v in (None, "None", "") else str(v)


def dot(color):
    return (f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background-color:{color};margin-right:6px;vertical-align:middle;"></span>')


def badge_247():
    return (f'<span style="display:inline-block;background-color:{GREEN_DARK};color:#ffffff;'
            f'font-size:10px;font-weight:700;letter-spacing:0.3px;padding:2px 7px;border-radius:3px;'
            f'margin-left:8px;vertical-align:middle;">24/7</span>')


def change_line(change):
    """change = (label, alt, neu) oder ("__raw__", text) für unlesbare Altdaten."""
    if len(change) == 2:
        return f'<div style="margin:3px 0;font-size:13px;color:{MUTED};">{_e(change[1])}</div>'
    label, old, new = change
    if is_gain_247(label, old, new):
        return (f'<div style="margin:3px 0;font-size:13px;"><span style="color:{GREEN_DARK};font-weight:700;">'
                f'Öffnungszeiten: neu 24/7</span>{badge_247()}</div>')
    if is_loss_247(label, old, new):
        detail = "keine Angabe mehr" if val(new) == "(leer)" else val(new)
        return (f'<div style="margin:3px 0;font-size:13px;color:{COLOR_GEAENDERT};font-weight:700;">'
                f'Öffnungszeiten: nicht mehr 24/7 <span style="font-weight:400;">({_e(detail)})</span></div>')
    return (f'<div style="margin:3px 0;font-size:13px;color:{INK};">'
            f'<span style="color:{MUTED};">{_e(label)}:</span> '
            f'<span style="color:#9CA3AF;text-decoration:line-through;">{_e(val(old))}</span>'
            f' &rarr; <strong style="font-weight:600;">{_e(val(new))}</strong></div>')


def card(entry):
    color = STATUS_COLORS[entry["status"]]
    link = (f'<a href="{_e(entry["url"])}" style="color:{GREEN_DARK};text-decoration:none;font-weight:600;">'
            f'Auf Karte ansehen &rarr;</a>') if entry.get("url") else ""
    hint = (f' <span style="color:{MUTED};font-size:12px;font-weight:400;">(kein Name in OSM)</span>'
            if SHOW_NO_NAME_HINT and not entry.get("has_name", True) else "")
    badge = badge_247() if entry.get("new_247") else ""
    addr = (f'<div style="font-size:13px;color:{MUTED};margin-top:2px;">{_e(entry["addr"])}</div>'
            if entry.get("addr") else "")
    changes = ""
    if entry.get("changes"):
        lines = "".join(change_line(c) for c in entry["changes"])
        changes = (f'<table role="presentation" width="100%" style="border-collapse:collapse;margin-top:10px;">'
                   f'<tr><td style="background-color:{CHANGE_BG};border-radius:6px;padding:8px 12px;">'
                   f'{lines}</td></tr></table>')
    return f'''
<table role="presentation" width="100%" style="border-collapse:separate;margin:0 0 12px 0;">
  <tr><td style="background-color:{CARD_BG};border:1px solid {RULE};border-left:4px solid {color};
                 border-radius:8px;padding:14px 18px;font-family:{FONT};">
    <table role="presentation" width="100%" style="border-collapse:collapse;">
      <tr>
        <td style="font-size:12px;font-weight:600;color:{color};">{dot(color)}{_e(entry["status"])}</td>
        <td align="right" style="font-size:12px;">{link}</td>
      </tr>
    </table>
    <div style="font-size:16px;font-weight:600;color:{INK};margin-top:8px;">{_e(entry["name"])}{hint}{badge}</div>
    {addr}
    {changes}
  </td></tr>
</table>'''


def summary_html(entries, statuses=("Neu", "Geändert", "Gelöscht")):
    """Zusammenfassungszeile; leer bei weniger als zwei Einträgen."""
    if len(entries) < 2:
        return ""
    cells = []
    for s in statuses:
        n = sum(1 for e in entries if e["status"] == s)
        if n:
            cells.append(f'<td style="padding-right:18px;white-space:nowrap;">{dot(STATUS_COLORS[s])}'
                         f'<strong style="color:{INK};">{n}</strong> {s.lower()}</td>')
    gains, losses = count_247(entries)
    if gains:
        cells.append(f'<td style="padding-right:18px;white-space:nowrap;">'
                     f'<strong style="color:{GREEN_DARK};">{gains}</strong> neu 24/7</td>')
    if losses:
        cells.append(f'<td style="white-space:nowrap;">'
                     f'<strong style="color:{COLOR_GEAENDERT};">{losses}</strong> nicht mehr 24/7</td>')
    if not cells:
        return ""
    return (f'<table role="presentation" style="margin:14px 0 4px 0;border-collapse:collapse;">'
            f'<tr style="font-family:{FONT};font-size:14px;color:{MUTED};">{"".join(cells)}</tr></table>')


def page(title, subtitle, entries, summary_block=None, body_html=None):
    """Seitenrahmen. body_html ersetzt die einfache Kartenliste (z.B. für Sektionen)."""
    if summary_block is None:
        summary_block = summary_html(entries)
    cards_html = body_html if body_html is not None else "".join(card(e) for e in entries)
    return f'''<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background-color:{PAGE_BG};">
<table role="presentation" width="100%" style="background-color:{PAGE_BG};border-collapse:collapse;"><tr><td align="center">
<table role="presentation" width="600" style="max-width:600px;border-collapse:collapse;"><tr><td style="padding:32px 20px;font-family:{FONT};">
<img src="{LOGO_URL}" alt="defikarte.ch" style="height:34px;"/>
<h1 style="font-family:{FONT};font-weight:700;font-size:20px;line-height:1.35;color:{GREEN_DARK};margin:24px 0 6px 0;">{_e(title)}</h1>
<p style="font-family:{FONT};font-size:13px;color:{MUTED};margin:0;">{_e(subtitle)}</p>
{summary_block}
<div style="margin-top:14px;">
{cards_html}
</div>
<p style="font-family:{FONT};font-size:11px;color:{MUTED};margin-top:24px;">Automatisch generiert von defikarte.ch</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
'''
