"""
Generiert die Workflow-Dateien aus kantone_config.json.

Seit der Umstellung auf einen einzigen Orchestrator-Workflow
(geojson-reporting-all.yml) übernimmt process_all_kantone.py die
komplette Kanton-Logik zur Laufzeit direkt aus kantone_config.json -
neue Kantone brauchen also KEINE neu generierte Workflow-Logik mehr.

Dieses Script generiert nur noch geojson-reporting-all.yml, den EINEN
Orchestrator-Workflow. Der Secrets-Env-Block muss weiterhin generiert werden,
weil GitHub Actions keine dynamischen Secret-Namen erlaubt.

Der wöchentliche Sammel-Report (reporting_mode
"immediate_new_deleted_weekly_changed") läuft ebenfalls im Orchestrator mit
und braucht keinen eigenen Workflow mehr.

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
      force_weekly:
        description: "Wochen-Reports jetzt senden (sonst Montag ab 07:00 UTC)"
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
          FORCE_WEEKLY: ${{{{ inputs.force_weekly || 'false' }}}}
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


def main():
    config = load_config()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    orchestrator = build_orchestrator_workflow(config)
    path = os.path.join(OUTPUT_DIR, "geojson-reporting-all.yml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(orchestrator)
    print(f"Erzeugt: {path}")


if __name__ == "__main__":
    main()
