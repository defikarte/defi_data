"""
Erzeugt das HTML für den wöchentlichen Änderungs-Report aus einer
pending_changes_<id>.json Datei (geschrieben von geojson_diff_be.py).

Verwendung:
    python build_weekly_report.py <pending_file> <kanton_name> <output_html>
"""

import json
import html
import sys
from datetime import datetime, timezone

DEFIKARTE_LOGO_URL = "https://assets.defikarte.ch/logo/logo_gruen.jpg"

GREEN_LIGHT = "#97C568"
GREEN_DARK  = "#144430"
INK         = "#1F2937"
MUTED       = "#6B7280"
RULE        = "#E5E7EB"
BG          = "#FFFFFF"
COLOR_GEAENDERT = "#E8A33D"

FONT = "'Poppins', Arial, Helvetica, sans-serif"


def maps_link(lon, lat, key=None):
    if key and key.startswith(("node/", "way/", "relation/")):
        return f'<a href="https://www.openstreetmap.org/{key}" style="color:{GREEN_DARK};">Karte</a>'
    if lon is not None and lat is not None:
        return f'<a href="https://www.google.com/maps?q={lat},{lon}" style="color:{GREEN_DARK};">Karte</a>'
    return ""


def badge_247():
    return (f'<span style="display:inline-block;background-color:{GREEN_DARK};color:#ffffff;'
            f'font-size:10px;font-weight:700;letter-spacing:0.3px;padding:2px 7px;'
            f'border-radius:3px;margin-left:8px;vertical-align:middle;">24/7</span>')


def dot(color):
    return (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background-color:{color};margin-right:7px;"></span>')


def render_changes(changes, size=13):
    if not changes:
        return ""
    parts = []
    for c in changes:
        label, old_v, new_v = c.get("label", ""), c.get("old"), c.get("new")
        gain_247 = (label == "Öffnungszeiten" and str(new_v) == "24/7")
        loss_247 = (label == "Öffnungszeiten" and str(old_v) == "24/7" and str(new_v) != "24/7")
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


def has_247_gain(changes):
    return any(c.get("label") == "Öffnungszeiten" and str(c.get("new")) == "24/7" for c in changes)


def main():
    pending_file = sys.argv[1]
    kanton_name = sys.argv[2]
    output_file = sys.argv[3]

    with open(pending_file, encoding="utf-8") as f:
        entries = json.load(f)

    rows = []
    for e in entries:
        lon, lat = e.get("lon"), e.get("lat")
        key = e.get("key", "")
        addr = e.get("address") or ""
        name = str(e.get("name") or "").strip()
        has_name = e.get("has_name", True)
        # Altbestand aus früherem Format ("(ohne Name)") sinnvoll ersetzen
        if not name or name == "(ohne Name)":
            has_name = False
            if addr:
                name, addr = addr, ""
            elif lat is not None and lon is not None:
                name = f"Standort {lat:.5f}, {lon:.5f}"
            else:
                name = "Unbenannter Defi"
        hint = "" if has_name else (f'<span style="color:{MUTED};font-size:12px;font-weight:400;"> '
                                    f'(kein Name in OSM)</span>')
        changes = e.get("changes", [])
        link = maps_link(lon, lat, key)

        addr_part = f'<span style="color:{MUTED};"> · {html.escape(addr)}</span>' if addr else ""
        changes_html = render_changes(changes)

        rows.append(f'''
        <table role="presentation" width="100%" style="border-collapse:collapse;">
          <tr>
            <td style="padding:12px 0;border-bottom:1px solid {RULE};">
              <span style="font-size:12px;color:{COLOR_GEAENDERT};font-weight:600;">{dot(COLOR_GEAENDERT)}Geändert</span><br>
              <span style="font-size:15px;font-weight:600;color:{INK};margin-top:4px;display:inline-block;">{html.escape(name)}</span>{hint}{addr_part}
              {changes_html}
              <div style="font-size:13px;margin-top:4px;">{link}</div>
            </td>
          </tr>
        </table>
        ''')

    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    gains = sum(1 for e in entries if any(
        c.get("label") == "Öffnungszeiten" and str(c.get("new")) == "24/7" for c in e.get("changes", [])))
    losses = sum(1 for e in entries if any(
        c.get("label") == "Öffnungszeiten" and str(c.get("old")) == "24/7" and str(c.get("new")) != "24/7"
        for c in e.get("changes", [])))
    summary_block = ""
    if len(entries) > 1 and (gains or losses):
        cells = []
        if gains:
            cells.append(f'<td style="padding-right:18px;"><strong style="color:{GREEN_DARK};">{gains}</strong> neu 24/7</td>')
        if losses:
            cells.append(f'<td><strong style="color:{COLOR_GEAENDERT};">{losses}</strong> nicht mehr 24/7</td>')
        summary_block = (f'<table role="presentation" style="margin:14px 0 0 0;border-collapse:collapse;">'
                         f'<tr style="font-family:{FONT};font-size:14px;color:{MUTED};">{"".join(cells)}</tr></table>')
    body_html = "".join(rows)

    output = f"""
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
Wöchentlicher Änderungs-Report – {html.escape(kanton_name)}
</h1>

<p style="font-family:{FONT};font-size:13px;color:{MUTED};margin:0;">
Stand {today} · {len(entries)} Eintrag{"e" if len(entries) != 1 else ""} geändert diese Woche
</p>

{summary_block}

<div style="font-family:{FONT};margin-top:16px;">
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

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"{output_file} geschrieben mit {len(entries)} Einträgen.")


if __name__ == "__main__":
    main()
