"""
Täglicher schweizweiter QS-Report (intern), nach Kanton gruppiert.

Vergleicht den Stand beim letzten Report (Commit-SHA in STATE_FILE) mit dem
aktuellen Stand im Arbeitsverzeichnis. Dadurch werden alle Änderungen seit dem
letzten Report erfasst, egal wie viele Overpass-Läufe dazwischen lagen.

Kantonszuordnung: Ein Defi gehört zu dem Kanton, in dessen
data/json/defis_kt_<kürzel>.geojson er vorkommt (gleiche Zuordnung wie die
Kantonsreports). Gelöschte Defis werden über die Kantonsfiles vom alten Stand
zugeordnet.

Ausgabe:
  - qs_report.html (nur wenn es Änderungen gibt)
  - STATE_FILE wird auf den aktuellen Commit gesetzt
  - in $GITHUB_ENV: HAS_REPORT, QS_SUBJECT
Beim allerersten Lauf (kein STATE_FILE) wird nur initialisiert, kein Report.
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from mail_common import (index, props, feature_entry, compute_changes, page, card,
                         summary_html, dot, STATUS_COLORS, FONT, INK, MUTED, RULE,
                         GREEN_DARK, GREEN_LIGHT, COLOR_GEAENDERT, _e)

CH_FILE = "data/json/defis_switzerland.geojson"
LI_FILE = "data/json/defis_liechtenstein.geojson"
KT_GLOB = "data/json/defis_kt_*.geojson"
KT_RE = re.compile(r"defis_kt_([a-z]{2})\.geojson$")
STATE_FILE = ".reporting/last_processed_sha_ch_qs.txt"
OUTPUT = "qs_report.html"

KANTONE = {
    "ag": "Aargau", "ai": "Appenzell Innerrhoden", "ar": "Appenzell Ausserrhoden",
    "be": "Bern", "bl": "Basel-Landschaft", "bs": "Basel-Stadt", "fr": "Freiburg",
    "ge": "Genf", "gl": "Glarus", "gr": "Graubünden", "ju": "Jura", "lu": "Luzern",
    "ne": "Neuenburg", "nw": "Nidwalden", "ow": "Obwalden", "sg": "St. Gallen",
    "sh": "Schaffhausen", "so": "Solothurn", "sz": "Schwyz", "tg": "Thurgau",
    "ti": "Tessin", "ur": "Uri", "vd": "Waadt", "vs": "Wallis", "zg": "Zug", "zh": "Zürich",
}
ORDER = {"Neu": 0, "Geändert": 1, "Gelöscht": 2}
UNASSIGNED = "__none__"
MULTI = "__multi__"


# ── Git / Daten ──────────────────────────────────────────────────────────────
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def load_current(path):
    if not os.path.exists(path):
        return {"features": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_at(sha, path):
    """Datei-Stand bei einem Commit; leer, falls sie damals nicht existierte."""
    r = git("show", f"{sha}:{path}")
    if r.returncode != 0:
        return {"features": []}
    return json.loads(r.stdout)


def canton_map(loader, paths):
    """OSM-Key -> Menge von Kantonskürzeln."""
    m = {}
    for path in paths:
        code = KT_RE.search(path).group(1)
        for k in index(loader(path).get("features", []) or []):
            m.setdefault(k, set()).add(code)
    return m


def diff(old_fc, new_fc):
    old_idx = index(old_fc.get("features", []) or [])
    new_idx = index(new_fc.get("features", []) or [])
    out = []
    for k in set(new_idx) - set(old_idx):
        out.append((k, feature_entry("Neu", new_idx[k])))
    for k in set(new_idx) & set(old_idx):
        ch = compute_changes(props(old_idx[k]), props(new_idx[k]))
        if ch:
            out.append((k, feature_entry("Geändert", new_idx[k], ch)))
    for k in set(old_idx) - set(new_idx):
        out.append((k, feature_entry("Gelöscht", old_idx[k])))
    return out


# ── Rendering ────────────────────────────────────────────────────────────────
def counts_inline(ents):
    parts = []
    for s in ("Neu", "Geändert", "Gelöscht"):
        n = sum(1 for x in ents if x["status"] == s)
        if n:
            parts.append(f'{dot(STATUS_COLORS[s])}<strong style="color:{INK};">{n}</strong> {s.lower()}')
    return " &nbsp; ".join(parts)


def overview(rows):
    dash = '<span style="color:#D1D5DB;">–</span>'
    head = "".join(
        f'<td align="center" style="padding:6px 8px;border-bottom:1px solid {RULE};font-size:12px;color:{MUTED};">'
        f'{dot(STATUS_COLORS[s])}{s}</td>' for s in ("Neu", "Geändert", "Gelöscht"))
    trs = []
    for label, ents in rows:
        cells = "".join(
            f'<td align="center" style="padding:6px 8px;border-bottom:1px solid {RULE};color:{INK};">'
            f'{sum(1 for x in ents if x["status"] == s) or dash}</td>'
            for s in ("Neu", "Geändert", "Gelöscht"))
        trs.append(f'<tr><td style="padding:6px 8px 6px 0;border-bottom:1px solid {RULE};color:{INK};">'
                   f'{_e(label)}</td>{cells}</tr>')
    return (f'<table role="presentation" width="100%" style="border-collapse:collapse;margin:18px 0 8px 0;'
            f'font-family:{FONT};font-size:14px;"><tr><td style="padding:6px 8px 6px 0;'
            f'border-bottom:1px solid {RULE};font-size:12px;color:{MUTED};">Kanton</td>{head}</tr>'
            f'{"".join(trs)}</table>')


def section(title, ents, warn=None):
    ents = sorted(ents, key=lambda x: (ORDER[x["status"]], x["name"].lower()))
    note = (f'<p style="font-family:{FONT};font-size:13px;color:{COLOR_GEAENDERT};margin:4px 0 10px 0;">'
            f'{_e(warn)}</p>') if warn else ""
    return (f'<div style="margin-top:28px;padding-top:16px;border-top:2px solid {GREEN_LIGHT};">'
            f'<div style="font-family:{FONT};font-size:17px;font-weight:700;color:{GREEN_DARK};">{_e(title)}</div>'
            f'<div style="font-family:{FONT};font-size:13px;color:{MUTED};margin:4px 0 12px 0;">'
            f'{counts_inline(ents)}</div>{note}{"".join(card(x) for x in ents)}</div>')


def set_env(**kv):
    path = os.environ.get("GITHUB_ENV")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


# ── Hauptablauf ──────────────────────────────────────────────────────────────
def main():
    head = git("rev-parse", "HEAD").stdout.strip()
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

    last = open(STATE_FILE, encoding="utf-8").read().strip() if os.path.exists(STATE_FILE) else ""
    if not last or git("cat-file", "-e", f"{last}^{{commit}}").returncode != 0:
        open(STATE_FILE, "w", encoding="utf-8").write(head)
        print(f"Initialisiert auf {head[:8]} – erster Report folgt beim nächsten Lauf.")
        set_env(HAS_REPORT="false")
        return
    if last == head:
        print("Seit dem letzten Report keine neuen Commits.")
        set_env(HAS_REPORT="false")
        return

    kt_paths = sorted(set(glob.glob(KT_GLOB))
                      | set(git("ls-tree", "--name-only", last, "data/json/").stdout.split()))
    kt_paths = [p for p in kt_paths if KT_RE.search(p)]
    map_new = canton_map(load_current, kt_paths)
    map_old = canton_map(lambda p: load_at(last, p), kt_paths)

    buckets = {}
    for key, entry in diff(load_at(last, CH_FILE), load_current(CH_FILE)):
        codes = (map_old if entry["status"] == "Gelöscht" else map_new).get(key) \
                or map_new.get(key) or map_old.get(key) or set()
        bucket = UNASSIGNED if not codes else (sorted(codes)[0] if len(codes) == 1 else MULTI)
        if bucket == MULTI:
            entry["addr"] = ((entry.get("addr") or "") + " · in: "
                             + ", ".join(c.upper() for c in sorted(codes))).lstrip(" ·")
        buckets.setdefault(bucket, []).append(entry)

    li_entries = [e for _, e in diff(load_at(last, LI_FILE), load_current(LI_FILE))]

    sections, rows = [], []
    for code in sorted((c for c in buckets if c in KANTONE), key=lambda c: KANTONE[c]):
        label = f"{KANTONE[code]} ({code.upper()})"
        rows.append((label, buckets[code]))
        sections.append(section(label, buckets[code]))
    unknown = [c for c in buckets if c not in KANTONE and c not in (UNASSIGNED, MULTI)]
    for code in sorted(unknown):  # Kantonsfile mit unbekanntem Kürzel
        rows.append((code.upper(), buckets[code]))
        sections.append(section(code.upper(), buckets[code]))
    if li_entries:
        rows.append(("Liechtenstein (FL)", li_entries))
        sections.append(section("Liechtenstein (FL)", li_entries))
    if MULTI in buckets:
        rows.append(("Mehreren Kantonen zugeordnet", buckets[MULTI]))
        sections.append(section("Mehreren Kantonen zugeordnet", buckets[MULTI],
                                "Diese Einträge kommen in mehr als einem Kantonsfile vor."))
    if UNASSIGNED in buckets:
        rows.append(("Nicht zuordenbar", buckets[UNASSIGNED]))
        sections.append(section("Nicht zuordenbar", buckets[UNASSIGNED],
                                "Diese Einträge sind im Schweiz-File, aber in keinem Kantonsfile – "
                                "Koordinaten bzw. Kantonsabfrage prüfen."))

    all_entries = [e for _, ents in rows for e in ents]
    open(STATE_FILE, "w", encoding="utf-8").write(head)

    if not all_entries:
        print("Keine inhaltlichen Änderungen seit dem letzten Report.")
        set_env(HAS_REPORT="false")
        return

    n_regions = sum(1 for label, _ in rows if label not in ("Nicht zuordenbar", "Mehreren Kantonen zugeordnet"))
    since = git("show", "-s", "--format=%cd", "--date=format:%d.%m.%Y %H:%M", last).stdout.strip()
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y, %H:%M UTC")
    n = len(all_entries)
    subtitle = f"Stand {now} · seit {since} · {n} Änderung{'en' if n != 1 else ''} in {n_regions} Gebiet{'en' if n_regions != 1 else ''}"

    html_mail = page("Schweizweite Defi-Änderungen (QS)", subtitle, all_entries,
                     summary_html(all_entries), body_html=overview(rows) + "".join(sections))
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html_mail)

    subject = f"QS: {n} Defi-Änderung{'en' if n != 1 else ''} in {n_regions} Gebiet{'en' if n_regions != 1 else ''}"
    set_env(HAS_REPORT="true", QS_SUBJECT=subject)
    print(f"{OUTPUT} geschrieben: {n} Einträge, {len(rows)} Sektionen.")


if __name__ == "__main__":
    sys.exit(main())
