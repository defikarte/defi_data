"""
Erzeugt diff.html mit allen neuen, geänderten und gelöschten Defis
zwischen zwei GeoJSON-Ständen (für alle Kantone mit reporting_mode "immediate").

Verwendung:
    python geojson_diff.py <alt.geojson> <neu.geojson>
"""

import json
import sys
from datetime import datetime, timezone

from mail_common import index, props, feature_entry, compute_changes, page, T


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


old_idx = index(load(sys.argv[1]).get("features", []) or [])
new_idx = index(load(sys.argv[2]).get("features", []) or [])

added = sorted(set(new_idx) - set(old_idx))
removed = sorted(set(old_idx) - set(new_idx))
common = sorted(set(new_idx) & set(old_idx))

entries = [feature_entry("Neu", new_idx[k]) for k in added]
for k in common:
    changes = compute_changes(props(old_idx[k]), props(new_idx[k]))
    if changes:
        entries.append(feature_entry("Geändert", new_idx[k], changes))
entries += [feature_entry("Gelöscht", old_idx[k]) for k in removed]

if not entries:
    sys.exit(0)

now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y, %H:%M UTC")
html_mail = page(T("title"), T("as_of", now=now_str), entries)

with open("diff.html", "w", encoding="utf-8") as f:
    f.write(html_mail)
