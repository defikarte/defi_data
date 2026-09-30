"""
BE-Variante: neue und gelöschte Defis gehen sofort raus (diff_immediate.html),
geänderte werden in einer Pending-Datei für den Wochenreport gesammelt.

Verwendung:
    python geojson_diff_be.py <alt.geojson> <neu.geojson> [pending_file]
"""

import json
import os
import sys
from datetime import datetime, timezone

from mail_common import (index, props, coords, address, display_name,
                         feature_entry, compute_changes, page)

pending_file = sys.argv[3] if len(sys.argv) > 3 else ".reporting/pending_changes_be.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


old_idx = index(load(sys.argv[1]).get("features", []) or [])
new_idx = index(load(sys.argv[2]).get("features", []) or [])

added = sorted(set(new_idx) - set(old_idx))
removed = sorted(set(old_idx) - set(new_idx))
common = sorted(set(new_idx) & set(old_idx))

# ── Geändert: strukturiert für den Wochenreport sammeln ─────────────────────
changed_entries = []
now_iso = datetime.now(timezone.utc).isoformat()
for k in common:
    np_ = props(new_idx[k])
    changes = compute_changes(props(old_idx[k]), np_)
    if not changes:
        continue
    lon, lat = coords(new_idx[k])
    name, has_name, name_is_addr = display_name(np_, lon, lat)
    changed_entries.append({
        "key": k,
        "name": name,
        "has_name": has_name,
        "address": None if name_is_addr else address(np_),
        "lon": lon,
        "lat": lat,
        "changes": [{"label": l, "old": o, "new": n} for l, o, n in changes],
        "detected_at": now_iso,
    })

os.makedirs(os.path.dirname(pending_file) or ".", exist_ok=True)
existing = []
if os.path.exists(pending_file):
    try:
        with open(pending_file, encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, ValueError):
        existing = []

by_key = {e["key"]: e for e in existing}
for e in changed_entries:
    by_key[e["key"]] = e

with open(pending_file, "w", encoding="utf-8") as f:
    json.dump(list(by_key.values()), f, ensure_ascii=False, indent=2)

print(f"Pending changes gespeichert: {len(changed_entries)} neu/aktualisiert, "
      f"{len(by_key)} total in {pending_file}")

# ── Sofort: Neu + Gelöscht ──────────────────────────────────────────────────
immediate = ([feature_entry("Neu", new_idx[k]) for k in added]
             + [feature_entry("Gelöscht", old_idx[k]) for k in removed])

if immediate:
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y, %H:%M UTC")
    html_mail = page("Neue und gelöschte Defis – Kanton Bern", f"Stand {now_str}", immediate)
    with open("diff_immediate.html", "w", encoding="utf-8") as f:
        f.write(html_mail)
    print(f"diff_immediate.html geschrieben: {len(immediate)} Einträge")
else:
    print("Keine sofortigen Änderungen (neu/gelöscht).")
