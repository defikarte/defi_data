"""
Generiert die Workflow-Dateien aus kantone_config.json.

Seit der Umstellung auf einen einzigen Orchestrator-Workflow
(geojson-reporting-all.yml) übernimmt process_all_kantone.py die
komplette Kanton-Logik zur Laufzeit direkt aus kantone_config.json -
neue Kantone brauchen also KEINE neu generierte Workflow-Logik mehr.

Dieses Script generiert nur noch:
1. geojson-reporting-all.yml - der EINE Orchestrator-Workflow. Der
   Secrets-Env-Block muss weiterhin generiert werden, weil GitHub
   Actions keine dynamischen Secret-Namen erlaubt.
2. geojson-weekly-changes-<id>.yml - für jeden Kanton mit
   reporting_mode "immediate_new_deleted_weekly_changed" (aktuell BE),
   bleibt als separater, seltener Cron-Workflow bestehen (kein
   Spam-Risiko da nur 1x/Woche).

Verwendung:
    python generate_workflows.py
"""

import json
import os

CONFIG_FILE = "kantone_config.json"
OUTPUT_DIR = ".github/workflows"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_secrets_env_block(config):
    """Baut den env:-Block mit allen benötigten Secrets für den Orchestrator."""
    lines = [
        '          MAIL_USER: ${{ secrets.MAIL_USER }}',
        '          MAIL_PASS: ${{ secrets.MAIL_PASS }}',
        '          MAIL_COPY: ${{ secrets.MAIL_COPY }}',
    ]
    seen = set()
    for kanton in config["kantone"]:
        secret_name = kanton["mail_recipient_secret"]
        if secret_name in seen:
            continue
        seen.add(secret_name)
        lines.append(f'          {secret_name}: ${{{{ secrets.{secret_name} }}}}')
    return "\n".join(lines)


def build_orchestrator_workflow(config):
    secrets_env = build_secrets_env_block(config)

    return f"""name: Reporting für alle Kunden
on:
  workflow_run:
    workflows: ["Get data from Overpass"]
    types: [completed]
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Nur simulieren, keine echten Mails senden"
        type: boolean
        default: false

jobs:
  process-and-mail:
    if: ${{{{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}}}
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout latest main
        uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Alle Kantone verarbeiten und Mails gestaffelt versenden
        env:
          DRY_RUN: ${{{{ inputs.dry_run || 'false' }}}}
{secrets_env}
        run: |
          python3 scripts/process_all_kantone.py

      - name: Reporting-State committen (nur falls sich etwas geändert hat)
        if: env.STATE_CHANGED == 'true'
        run: |
          set -euo pipefail

          git config user.name "defikarte.ch Reporting Bot"
          git config user.email "chrigi@chnuessli.ch"

          git add .reporting/

          git commit -m "update reporting state (alle Kantone)" || exit 0

          for i in 1 2 3; do
            git pull --rebase origin main && git push origin HEAD:main && break
            echo "Push failed, retry $i..."
            sleep 2
          done

      - name: Lauf als fehlgeschlagen markieren, falls ein Kanton Fehler hatte
        if: env.REPORTING_ERRORS != '0'
        run: |
          echo "::error::$REPORTING_ERRORS Kanton(e) mit Fehler - Details in der Zusammenfassung dieses Laufs."
          exit 1
"""


def build_weekly_workflow(kanton):
    kid = kanton["id"]
    name = kanton["name"]
    recipient_secret = kanton["mail_recipient_secret"]
    cc_line = "\n          cc: ${{ secrets.MAIL_COPY }}" if kanton.get("use_cc") else ""

    return f"""name: Wöchentlicher Änderungs-Report {name}
on:
  schedule:
    - cron: "16 7 * * 1"   # jeden Montag um 07:00 UTC
  workflow_dispatch:

jobs:
  weekly-report:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout latest main
        uses: actions/checkout@v4
        with:
          ref: main

      - name: Check if pending changes exist
        run: |
          FILE=".reporting/pending_changes_{kid}.json"
          if [ -f "$FILE" ] && [ -s "$FILE" ]; then
            COUNT=$(python3 -c "import json; data=json.load(open('$FILE')); print(len(data))")
            if [ "$COUNT" -gt "0" ]; then
              echo "HAS_PENDING=true" >> $GITHUB_ENV
              echo "PENDING_COUNT=$COUNT" >> $GITHUB_ENV
            else
              echo "HAS_PENDING=false" >> $GITHUB_ENV
            fi
          else
            echo "HAS_PENDING=false" >> $GITHUB_ENV
          fi

      - name: Setup Python
        if: env.HAS_PENDING == 'true'
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Weekly-HTML generieren
        if: env.HAS_PENDING == 'true'
        run: |
          python3 scripts/build_weekly_report.py \\
            .reporting/pending_changes_{kid}.json \\
            "{name}" \\
            diff_weekly.html

      - name: Weekly-Mail versenden
        if: env.HAS_PENDING == 'true'
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: asmtp.mail.hostpoint.ch
          server_port: 587
          secure: false
          username: ${{{{ secrets.MAIL_USER }}}}
          password: ${{{{ secrets.MAIL_PASS }}}}
          subject: "Wöchentlicher Änderungs-Report – {name} (${{{{ env.PENDING_COUNT }}}} Änderungen)"
          html_body: file://diff_weekly.html
          to: ${{{{ secrets.{recipient_secret} }}}}{cc_line}
          from: defikarte.ch Reports

      - name: Pending changes leeren nach Versand
        if: env.HAS_PENDING == 'true'
        run: |
          set -euo pipefail
          echo "[]" > .reporting/pending_changes_{kid}.json

          git config user.name "defikarte.ch Reporting Bot"
          git config user.email "chrigi@chnuessli.ch"
          git add .reporting/pending_changes_{kid}.json

          rm -f diff_weekly.html
          git commit -m "clear pending changes {kid} after weekly report"

          for i in 1 2 3; do
            git pull --rebase origin main && git push origin HEAD:main && break
            echo "Push failed, retry $i..."
            sleep 2
          done
"""


def main():
    config = load_config()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    orchestrator = build_orchestrator_workflow(config)
    path = os.path.join(OUTPUT_DIR, "geojson-reporting-all.yml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(orchestrator)
    print(f"Erzeugt: {path}")

    for kanton in config["kantone"]:
        if kanton.get("reporting_mode") == "immediate_new_deleted_weekly_changed":
            weekly = build_weekly_workflow(kanton)
            weekly_path = os.path.join(OUTPUT_DIR, f"geojson-weekly-changes-{kanton['id']}.yml")
            with open(weekly_path, "w", encoding="utf-8") as f:
                f.write(weekly)
            print(f"Erzeugt: {weekly_path}")


if __name__ == "__main__":
    main()
