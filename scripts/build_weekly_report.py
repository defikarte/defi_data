"""
Erzeugt das HTML für den wöchentlichen Änderungs-Report aus einer
pending_changes_<id>.json Datei (geschrieben von geojson_diff_be.py).

Versteht auch Einträge im alten Format (Änderungen als Textzeile
"feld: 'alt' → 'neu'", Name "(ohne Name)").

Verwendung:
    python build_weekly_report.py <pending_file> <kanton_name> <output_html>
"""

import json
import re
import sys
from datetime import datetime, timezone

from mail_common import FIELD_LABELS, map_url, page, summary_html

_OLD_FORMAT = re.compile(r"^(.*?): '(.*)' \u2192 '(.*)'$", re.DOTALL)


def normalize_change(c):
    """Neues Format (dict) oder altes Format (Text) -> (label, alt, neu) bzw. ("__raw__", text)."""
    if isinstance(c, dict):
        return (c.get("label", ""), c.get("old"), c.get("new"))
    m = _OLD_FORMAT.match(str(c))
    if not m:
        return ("__raw__", str(c))
    key, old_v, new_v = m.groups()
    to_val = lambda v: None if v == "None" else v
    return (FIELD_LABELS.get(key, key), to_val(old_v), to_val(new_v))


def to_entry(e):
    lon, lat = e.get("lon"), e.get("lat")
    name = str(e.get("name") or "").strip()
    addr = e.get("address") or None
    has_name = e.get("has_name", True)
    if not name or name == "(ohne Name)":
        has_name = False
        if addr:
            name, addr = addr, None
        elif lat is not None and lon is not None:
            name = f"Standort {lat:.5f}, {lon:.5f}"
        else:
            name = "Unbenannter Defi"
    return {
        "status": "Geändert",
        "name": name,
        "has_name": has_name,
        "addr": addr,
        "url": map_url(lon, lat, e.get("key")),
        "new_247": False,
        "changes": [normalize_change(c) for c in e.get("changes", [])],
    }


def main():
    pending_file, kanton_name, output_file = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(pending_file, encoding="utf-8") as f:
        entries = [to_entry(e) for e in json.load(f)]

    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    n = len(entries)
    subtitle = f"Stand {today} · {n} Eintrag{'e' if n != 1 else ''} geändert diese Woche"

    # Anzahl steht bereits im Untertitel -> Zusammenfassung zeigt nur 24/7-Infos
    summary = summary_html(entries, statuses=())

    html_mail = page(f"Wöchentlicher Änderungs-Report – {kanton_name}", subtitle, entries, summary)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_mail)

    print(f"{output_file} geschrieben mit {n} Einträgen.")


if __name__ == "__main__":
    main()
