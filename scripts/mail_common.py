"""
Gemeinsame Bausteine für alle Report-Mails (geojson_diff.py,
geojson_diff_be.py, build_weekly_report.py).

Design-Änderungen (Farben, Karten, Seitenrahmen) nur hier vornehmen.

Sprache: über die Umgebungsvariable REPORT_LANG ("de" oder "fr"), die
process_all_kantone.py pro Kanton aus kantone_config.json ("language") setzt.
Ohne Angabe wird Deutsch verwendet. Intern bleiben Status-Schlüssel und
Feldnamen deutsch; übersetzt wird nur bei der Ausgabe.
"""

import html
import math
import os
import re

# ── defikarte.ch CI ──────────────────────────────────────────────────────────
# Farben aus den Design-Tokens der Website (Figma: primary-*, graustufen-*).
# Logo: Positiv-Version (dunkelgrün) auf weissem Grund – offenes Layout ohne
# farbige Kopf-/Fussbalken, damit Partner-Logos im Original stehen können.
LOGO_URL = "https://assets.defikarte.ch/logo/logo_positiv.png"
LOGO_WIDTH = 188                # Seitenverhältnis 765×139 -> ca. 34px hoch
GREEN_LIGHT = "#98C867"         # primary-100-green-02
GREEN_MID = "#30805D"           # primary-100-green-03
GREEN_DARK = "#154430"          # primary-100-green-04
INK = "#333333"                 # graustufen-grau-e
MUTED = "#666666"               # graustufen-grau-d
RULE = "#E5E5E5"                # graustufen-grau-a
PAGE_BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
CHANGE_BG = "#F5F7F6"
SITE_URL = "https://defikarte.ch"
# "Auf Karte ansehen" führt auf defikarte.ch: Kartenausschnitt über den Hash
# (#zoom/lat/lon), ?aed=<OSM-Node-ID> öffnet dort den Detailmarker.
DEFIKARTE_MAP_URL = f"{SITE_URL}/map"
DEFIKARTE_ZOOM = 19
FONT = "'Poppins', Arial, Helvetica, sans-serif"

# ── Partner-Logo oben rechts ─────────────────────────────────────────────────
# Pro Kanton über "partner_logo" in kantone_config.json (-> REPORT_PARTNER).
# PARTNER_SHOW_LABEL = True zeigt "in Zusammenarbeit mit" über dem Logo
# (dann wird "label_width" statt "width" verwendet).
PARTNER_LOGOS = {
    "surevive": {"url": "https://assets.defikarte.ch/logo/surevive.png", "alt": "sureVIVE",
                 "width": 120, "label_width": 100},
}
PARTNER_SHOW_LABEL = True
PARTNER = PARTNER_LOGOS.get(os.environ.get("REPORT_PARTNER", "").strip().lower())

COLOR_NEU = GREEN_LIGHT
COLOR_GEAENDERT = "#FFA52F"     # secondary-orange-03
COLOR_GELOESCHT = "#DC2626"
STATUS_COLORS = {"Neu": COLOR_NEU, "Geändert": COLOR_GEAENDERT, "Gelöscht": COLOR_GELOESCHT}
# Status-Pills: (Hintergrund, Text) – Text dunkler für Lesbarkeit auf hellem Grund
STATUS_PILL = {"Neu": ("#EAF4E1", "#1C593F"), "Geändert": ("#FFF0DB", "#8A4B00"),
               "Gelöscht": ("#FDE4E4", "#B91C1C")}
COLOR_WARN_TEXT = STATUS_PILL["Geändert"][1]

SHOW_NO_NAME_HINT = False  # "(kein Name in OSM)" bei Einträgen ohne name-Tag

FIELD_LABELS = {
    "name": "Name", "status": "Status", "operator": "Betreiber", "phone": "Telefon",
    "access": "Zugang", "opening_hours": "Öffnungszeiten",
    "defibrillator:location": "Standortbeschreibung", "description": "Beschreibung",
    "level": "Stockwerk", "addr:street": "Strasse", "addr:housenumber": "Hausnummer",
    "addr:postcode": "PLZ", "addr:city": "Ort", "indoor": "Innenbereich",
}
RELEVANT_FIELDS = list(FIELD_LABELS.keys())
OPENING_LABEL = FIELD_LABELS["opening_hours"]

# Verschiebung: wird gemeldet, wenn der Defi mindestens so weit versetzt wurde.
# Pro Kanton über "move_threshold_m" in kantone_config.json (-> REPORT_MOVE_THRESHOLD_M).
MOVE_LABEL = "Standort"
MOVE_THRESHOLD_M = float(os.environ.get("REPORT_MOVE_THRESHOLD_M") or 25)


# ── Sprache ──────────────────────────────────────────────────────────────────
LANG = os.environ.get("REPORT_LANG", "de").strip().lower()
if LANG not in ("de", "fr"):
    LANG = "de"

TEXTS = {
    "de": {
        "title": "Änderungen an Defibrillatoren im Einzugsgebiet",
        "as_of": "Stand {now}",
        "Neu": "Neu", "Geändert": "Geändert", "Gelöscht": "Gelöscht",
        "sum_Neu": ("neu", "neu"),
        "sum_Geändert": ("geändert", "geändert"),
        "sum_Gelöscht": ("gelöscht", "gelöscht"),
        "sum_gain_247": "neu 24/7",
        "sum_loss_247": "nicht mehr 24/7",
        "map_link": "Auf Karte ansehen",
        "no_name_hint": "(kein Name in OSM)",
        "location": "Standort",
        "unnamed": "Defi ohne Bezeichnung",
        "empty": "(leer)",
        "added": "ergänzt",
        "removed": "entfernt",
        "gain_247": "Öffnungszeiten: neu 24/7",
        "loss_247": "Öffnungszeiten: nicht mehr 24/7",
        "no_info": "keine Angabe mehr",
        "moved": "verschoben um {dist}",
        "old_location": "alter Standort",
        "osm_history": "Verlauf in OSM",
        "footer": "Automatisch generiert von defikarte.ch",
        "partner_label": "in Zusammenarbeit mit",
    },
    "fr": {
        "title": "Modifications des défibrillateurs dans votre secteur",
        "as_of": "État au {now}",
        "Neu": "Nouveau", "Geändert": "Modifié", "Gelöscht": "Supprimé",
        "sum_Neu": ("nouveau", "nouveaux"),
        "sum_Geändert": ("modifié", "modifiés"),
        "sum_Gelöscht": ("supprimé", "supprimés"),
        "sum_gain_247": "désormais 24/7",
        "sum_loss_247": "plus en 24/7",
        "map_link": "Voir sur la carte",
        "no_name_hint": "(sans nom dans OSM)",
        "location": "Emplacement",
        "unnamed": "Défibrillateur sans désignation",
        "empty": "(vide)",
        "added": "ajouté",
        "removed": "supprimé",
        "gain_247": "Horaires d\u2019ouverture\u00a0: désormais 24/7",
        "loss_247": "Horaires d\u2019ouverture\u00a0: plus en 24/7",
        "no_info": "plus aucune indication",
        "moved": "déplacé de {dist}",
        "old_location": "ancien emplacement",
        "osm_history": "historique dans OSM",
        "footer": "Généré automatiquement par defikarte.ch",
        "partner_label": "en collaboration avec",
    },
}

FIELD_LABELS_FR = {
    "Name": "Nom", "Status": "Statut", "Betreiber": "Exploitant", "Telefon": "Téléphone",
    "Zugang": "Accès", "Öffnungszeiten": "Horaires d\u2019ouverture",
    "Standortbeschreibung": "Description de l\u2019emplacement", "Beschreibung": "Description",
    "Stockwerk": "Étage", "Strasse": "Rue", "Hausnummer": "Numéro",
    "PLZ": "NPA", "Ort": "Localité", "Innenbereich": "À l\u2019intérieur",
    "Standort": "Emplacement",
}


# Lesbare Anzeige für OSM-Werte (Feld -> Wert -> Text); unbekannte Werte bleiben roh.
VALUE_LABELS = {
    "de": {
        "Innenbereich": {"yes": "ja", "no": "nein"},
        "Zugang": {"yes": "öffentlich", "public": "öffentlich", "permissive": "öffentlich (geduldet)",
                   "customers": "nur Kundschaft", "private": "privat", "permit": "mit Bewilligung",
                   "no": "nicht zugänglich"},
    },
    "fr": {
        "Innenbereich": {"yes": "oui", "no": "non"},
        "Zugang": {"yes": "public", "public": "public", "permissive": "public (toléré)",
                   "customers": "clientèle uniquement", "private": "privé", "permit": "sur autorisation",
                   "no": "non accessible"},
    },
}


def T(key, **kw):
    text = TEXTS[LANG].get(key, TEXTS["de"].get(key, key))
    return text.format(**kw) if kw else text


def label_out(label):
    """Interner (deutscher) Feldname -> Anzeige in der Report-Sprache."""
    return FIELD_LABELS_FR.get(label, label) if LANG == "fr" else label


def colon():
    """Doppelpunkt nach Typografie der Sprache (fr: geschütztes Leerzeichen davor)."""
    return "\u00a0:" if LANG == "fr" else ":"


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
        return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=19/{lat:.6f}/{lon:.6f}"
    return None


def defikarte_url(lon, lat, key=None):
    """Link auf den Defi auf defikarte.ch; ohne Koordinaten Fallback auf map_url."""
    if lon is None or lat is None:
        return map_url(lon, lat, key)
    m = re.match(r"^node/(\d+)$", key or "")
    query = f"?aed={m.group(1)}" if m else ""
    return f"{DEFIKARTE_MAP_URL}{query}#{DEFIKARTE_ZOOM}/{lat:.6f}/{lon:.6f}"


def truncate(s, n=140):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "\u2026"


def display_name(p, lon, lat):
    """Liefert (titel, hat_eigenen_namen, titel_ist_adresse)."""
    name = str(p.get("name") or "").strip()
    if name:
        return name, True, False
    operator = str(p.get("operator") or "").strip()
    if operator:
        return truncate(operator, 80), False, False
    location = location_text(p)
    if location:
        return truncate(location, 80), False, False
    addr = address(p)
    if addr:
        return addr, False, True
    return T("unnamed"), False, False


def location_text(p):
    return str(p.get("defibrillator:location")
               or p.get("defibrillator:location:de")
               or p.get("description") or "").strip()


def detail_line(p, title):
    """Standortbeschreibung als eigene Zeile unter dem Titel (falls nicht schon Titel)."""
    location = location_text(p)
    return truncate(location) if location and truncate(location, 80) != title else None


def coords_line(lon, lat):
    return f"{T('location')} {lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else None


def feature_entry(status, feature, changes=None):
    """Baut aus einem GeoJSON-Feature einen Karten-Eintrag."""
    p = props(feature)
    lon, lat = coords(feature)
    name, has_name, name_is_addr = display_name(p, lon, lat)
    detail = detail_line(p, name)
    # Koordinaten nur, wenn sonst gar nichts den Defi beschreibt
    fallback = coords_line(lon, lat) if name == T("unnamed") and not detail else None
    return {
        "status": status,
        "name": name,
        "has_name": has_name,
        "detail": detail,
        "addr": None if name_is_addr else (address(p) or fallback),
        # Gelöschte Defis gibt es auf defikarte.ch nicht mehr -> OSM-Link (zeigt auch die Historie)
        "url": (map_url if status == "Gelöscht" else defikarte_url)(lon, lat, get_key(feature)),
        "key": get_key(feature),
        "new_247": status == "Neu" and p.get("opening_hours") == "24/7",
        "changes": changes or [],
    }


def compute_changes(old_p, new_p):
    """Liste von (label, alt, neu) für alle relevanten geänderten Felder."""
    return [(FIELD_LABELS[f], old_p.get(f), new_p.get(f))
            for f in RELEVANT_FIELDS if old_p.get(f) != new_p.get(f)]


def distance_m(lon1, lat1, lon2, lat2):
    """Luftlinie in Metern (Haversine)."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def compute_move(old_f, new_f):
    """[(MOVE_LABEL, "lat,lon alt", "lat,lon neu")] ab MOVE_THRESHOLD_M, sonst []."""
    lon1, lat1 = coords(old_f)
    lon2, lat2 = coords(new_f)
    if None in (lon1, lat1, lon2, lat2):
        return []
    if distance_m(lon1, lat1, lon2, lat2) < MOVE_THRESHOLD_M:
        return []
    return [(MOVE_LABEL, f"{lat1:.6f},{lon1:.6f}", f"{lat2:.6f},{lon2:.6f}")]


def feature_changes(old_f, new_f):
    """Verschiebung plus geänderte Felder zwischen zwei Ständen desselben Defis."""
    return compute_move(old_f, new_f) + compute_changes(props(old_f), props(new_f))


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


def is_empty(v):
    return v in (None, "None", "")


def val(v, label=None):
    if is_empty(v):
        return T("empty")
    return VALUE_LABELS.get(LANG, {}).get(label, {}).get(str(v), str(v))


def dot(color):
    return (f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background-color:{color};margin-right:6px;vertical-align:middle;"></span>')


def pill(text, bg, fg, size=11):
    return (f'<span style="display:inline-block;background-color:{bg};color:{fg};font-size:{size}px;'
            f'font-weight:600;line-height:1.4;padding:3px 10px;border-radius:50px;vertical-align:middle;">'
            f'{_e(text)}</span>')


def badge_247():
    return (f'<span style="display:inline-block;background-color:{GREEN_DARK};color:#ffffff;'
            f'font-size:10px;font-weight:600;letter-spacing:0.3px;padding:2px 8px;border-radius:50px;'
            f'margin-left:8px;vertical-align:middle;">24/7</span>')


def format_distance(m):
    if m < 1000:
        return f"{round(m)} m"
    km = f"{m / 1000:.1f}"
    return f"{km.replace('.', ',') if LANG == 'fr' else km} km"


def old_location_link(lon, lat, key=None):
    """OSM-History des Nodes (zeigt alle Positionen und wer verschoben hat);
    ohne Node-ID ein OSM-Marker am alten Standort."""
    if key and key.startswith(("node/", "way/", "relation/")):
        return f"https://www.openstreetmap.org/{key}/history", T("osm_history")
    return map_url(lon, lat), T("old_location")


def move_line(old, new, key=None):
    """Zeile für eine Verschiebung; old/new als "lat,lon"."""
    try:
        lat1, lon1 = (float(x) for x in str(old).split(","))
        lat2, lon2 = (float(x) for x in str(new).split(","))
    except ValueError:
        return f'<div style="margin:3px 0;font-size:13px;color:{MUTED};">{_e(label_out(MOVE_LABEL))}</div>'
    dist = format_distance(distance_m(lon1, lat1, lon2, lat2))
    url, text = old_location_link(lon1, lat1, key)
    old_link = f' <a href="{_e(url)}" style="color:{GREEN_DARK};font-size:12px;">({_e(text)})</a>'
    return (f'<div style="margin:3px 0;font-size:13px;color:{INK};">'
            f'<span style="color:{MUTED};">{_e(label_out(MOVE_LABEL))}{colon()}</span> '
            f'<strong style="font-weight:600;">{_e(T("moved", dist=dist))}</strong>{old_link}</div>')


def change_line(change, key=None):
    """change = (label, alt, neu) oder ("__raw__", text) für unlesbare Altdaten."""
    if len(change) == 2:
        return f'<div style="margin:3px 0;font-size:13px;color:{MUTED};">{_e(change[1])}</div>'
    label, old, new = change
    if label == MOVE_LABEL:
        return move_line(old, new, key)
    if is_gain_247(label, old, new):
        return (f'<div style="margin:3px 0;font-size:13px;"><span style="color:{GREEN_DARK};font-weight:600;">'
                f'{_e(T("gain_247"))}</span>{badge_247()}</div>')
    if is_loss_247(label, old, new):
        detail = T("no_info") if is_empty(new) else str(new)
        return (f'<div style="margin:3px 0;font-size:13px;color:{COLOR_WARN_TEXT};font-weight:600;">'
                f'{_e(T("loss_247"))} <span style="font-weight:400;">({_e(detail)})</span></div>')
    head = f'<span style="color:{MUTED};">{_e(label_out(label))}{colon()}</span> '
    note = lambda key: f' <span style="color:{MUTED};font-size:12px;">({_e(T(key))})</span>'
    old_html = f'<span style="color:#999999;text-decoration:line-through;">{_e(val(old, label))}</span>'
    new_html = f'<strong style="font-weight:600;">{_e(val(new, label))}</strong>'
    if is_empty(new):
        body = old_html + note("removed")
    elif is_empty(old):
        body = new_html + note("added")
    else:
        body = f'{old_html} &rarr; {new_html}'
    return f'<div style="margin:3px 0;font-size:13px;color:{INK};">{head}{body}</div>'




def card(entry):
    bg, fg = STATUS_PILL[entry["status"]]
    link = (f'<a href="{_e(entry["url"])}" style="display:inline-block;border:1px solid {GREEN_DARK};'
            f'border-radius:50px;padding:3px 12px;color:{GREEN_DARK};text-decoration:none;font-weight:500;'
            f'font-size:12px;line-height:1.4;">{_e(T("map_link"))} &rarr;</a>') if entry.get("url") else ""
    hint = (f' <span style="color:{MUTED};font-size:12px;font-weight:400;">{_e(T("no_name_hint"))}</span>'
            if SHOW_NO_NAME_HINT and not entry.get("has_name", True) else "")
    badge = badge_247() if entry.get("new_247") else ""
    detail = (f'<div style="font-size:13px;color:{INK};margin-top:2px;">{_e(entry["detail"])}</div>'
              if entry.get("detail") else "")
    addr = (f'<div style="font-size:13px;color:{MUTED};margin-top:2px;">{_e(entry["addr"])}</div>'
            if entry.get("addr") else "")
    changes = ""
    if entry.get("changes"):
        lines = "".join(change_line(c, entry.get("key")) for c in entry["changes"])
        changes = (f'<table role="presentation" width="100%" style="border-collapse:collapse;margin-top:12px;">'
                   f'<tr><td style="background-color:{CHANGE_BG};border-radius:12px;padding:10px 14px;">'
                   f'{lines}</td></tr></table>')
    return f'''
<table role="presentation" width="100%" style="border-collapse:separate;margin:0 0 12px 0;">
  <tr><td style="background-color:{CARD_BG};border:1px solid {RULE};border-radius:16px;padding:16px 20px;font-family:{FONT};">
    <table role="presentation" width="100%" style="border-collapse:collapse;">
      <tr>
        <td valign="middle">{pill(T(entry["status"]), bg, fg)}</td>
        <td align="right" valign="middle">{link}</td>
      </tr>
    </table>
    <div style="font-size:16px;font-weight:600;color:{INK};margin-top:10px;">{_e(entry["name"])}{hint}{badge}</div>
    {detail}
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
                         f'<strong style="color:{INK};">{n}</strong> {T("sum_" + s)[0 if n == 1 else 1]}</td>')
    gains, losses = count_247(entries)
    if gains:
        cells.append(f'<td style="padding-right:18px;white-space:nowrap;">'
                     f'<strong style="color:{GREEN_DARK};">{gains}</strong> {T("sum_gain_247")}</td>')
    if losses:
        cells.append(f'<td style="white-space:nowrap;">'
                     f'<strong style="color:{COLOR_WARN_TEXT};">{losses}</strong> {T("sum_loss_247")}</td>')
    if not cells:
        return ""
    return (f'<table role="presentation" style="margin:14px 0 4px 0;border-collapse:collapse;">'
            f'<tr style="font-family:{FONT};font-size:14px;color:{MUTED};">{"".join(cells)}</tr></table>')


def header_html():
    """Kopfzeile auf Weiss: defikarte.ch links, optional Partner-Logo (Original) rechts,
    darunter die Verlaufslinie wie die Website-Buttons (green-03 -> green-02)."""
    logo = (f'<a href="{SITE_URL}" style="text-decoration:none;"><img src="{LOGO_URL}" alt="defikarte.ch" '
            f'width="{LOGO_WIDTH}" style="width:{LOGO_WIDTH}px;height:auto;display:block;border:0;"/></a>')
    right = ""
    if PARTNER and PARTNER_SHOW_LABEL:
        w = PARTNER["label_width"]
        right = (f'<td align="right" valign="middle" style="font-family:{FONT};font-size:10px;color:{MUTED};line-height:1;">'
                 f'<div style="margin-bottom:6px;">{_e(T("partner_label"))}</div>'
                 f'<img src="{PARTNER["url"]}" alt="{_e(PARTNER["alt"])}" width="{w}" '
                 f'style="width:{w}px;height:auto;display:inline-block;border:0;"/></td>')
    elif PARTNER:
        w = PARTNER["width"]
        right = (f'<td align="right" valign="middle"><img src="{PARTNER["url"]}" alt="{_e(PARTNER["alt"])}" '
                 f'width="{w}" style="width:{w}px;height:auto;display:block;border:0;"/></td>')
    return (f'<table role="presentation" width="100%" style="border-collapse:collapse;"><tr>'
            f'<td style="padding:4px 0 18px 0;">'
            f'<table role="presentation" width="100%" style="border-collapse:collapse;"><tr>'
            f'<td align="left" valign="middle">{logo}</td>{right}</tr></table></td></tr>'
            f'<tr><td height="3" style="height:3px;line-height:3px;font-size:0;background-color:{GREEN_LIGHT};'
            f'background-image:linear-gradient(90deg,{GREEN_MID},{GREEN_LIGHT});">&nbsp;</td></tr></table>')


def footer_html():
    link = f'<a href="{SITE_URL}" style="color:{GREEN_MID};text-decoration:none;font-weight:500;">defikarte.ch</a>'
    text = _e(T("footer")).replace("defikarte.ch", link)
    return (f'<table role="presentation" width="100%" style="border-collapse:collapse;"><tr>'
            f'<td style="border-top:1px solid {RULE};padding:16px 0 4px 0;'
            f'font-family:{FONT};font-size:12px;color:{MUTED};">{text}</td></tr></table>')


def page(title, subtitle, entries, summary_block=None, body_html=None):
    """Seitenrahmen. body_html ersetzt die einfache Kartenliste (z.B. für Sektionen)."""
    if summary_block is None:
        summary_block = summary_html(entries)
    cards_html = body_html if body_html is not None else "".join(card(e) for e in entries)
    return f'''<html lang="{LANG}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600&display=swap" rel="stylesheet"/>
</head>
<body style="margin:0;padding:0;background-color:{PAGE_BG};">
<table role="presentation" width="100%" style="background-color:{PAGE_BG};border-collapse:collapse;"><tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="600" style="max-width:600px;width:100%;border-collapse:collapse;"><tr><td style="font-family:{FONT};">
{header_html()}
<div style="padding:24px 0 16px 0;">
<h1 style="font-family:{FONT};font-weight:600;font-size:22px;line-height:1.35;color:{GREEN_DARK};margin:0 0 6px 0;">{_e(title)}</h1>
<p style="font-family:{FONT};font-size:13px;color:{MUTED};margin:0;">{_e(subtitle)}</p>
{summary_block}
<div style="margin-top:16px;">
{cards_html}
</div>
</div>
{footer_html()}
</td></tr></table>
</td></tr></table>
</body>
</html>
'''
