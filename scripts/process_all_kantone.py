"""
Verarbeitet ALLE Kantone aus kantone_config.json in einem einzigen Lauf,
sequenziell, mit einer kleinen Pause zwischen tatsächlich versendeten Mails.

Vorteile gegenüber 13 separaten Workflows:
- Nur EIN Workflow läuft pro Overpass-Run -> keine parallelen SMTP-Verbindungen
  die wie Spam aussehen
- Nur EIN Git-Commit am Ende -> keine Push-Kollisionen zwischen Kantonen
- Neue Kantone brauchen nur einen Eintrag in kantone_config.json, keine
  Workflow-Generierung mehr nötig (ausser für den Secret-Env-Block)

Verwendung (im Workflow):
    python3 scripts/process_all_kantone.py

Erwartet folgende Umgebungsvariablen:
    MAIL_USER, MAIL_PASS, MAIL_COPY
    sowie je einen Eintrag pro Kanton, benannt nach dessen
    "mail_recipient_secret" aus der Config (z.B. MAIL_RECIPIENT_SO)

Schreibt am Ende STATE_CHANGED=true/false in $GITHUB_ENV, damit der
Workflow weiss ob ein abschliessender Commit nötig ist.
"""

import json
import os
import subprocess
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CONFIG_FILE = "kantone_config.json"

# Pause zwischen tatsächlich versendeten Mails, um nicht wie ein
# Massenversand aus einer Quelle auszusehen (Spam-Filter).
SEND_DELAY_SECONDS = 8

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_geojson_sha(path):
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", path],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def has_changed(sha, path):
    result = subprocess.run(["git", "diff", "--quiet", f"{sha}^..{sha}", "--", path])
    return result.returncode != 0


def show_old_version(sha, path, out_path):
    with open(out_path, "wb") as f:
        subprocess.run(["git", "show", f"{sha}^:{path}"], stdout=f, check=True)


def send_mail(subject, html_body, to_addr, cc_addr=None):
    if DRY_RUN:
        print(f"[DRY RUN] Würde Mail senden: '{subject}' an {to_addr}"
              + (f" (CC {cc_addr})" if cc_addr else ""))
        return

    user = os.environ["MAIL_USER"]
    password = os.environ["MAIL_PASS"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"defikarte.ch Reports <{user}>"
    msg["To"] = to_addr

    recipients = [to_addr]
    if cc_addr:
        msg["Cc"] = cc_addr
        recipients.append(cc_addr)

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Kurze Retries für den Fall, dass es sich um einen transienten
    # Fehler handelt (z.B. kurzzeitige Überlastung). Bei einem
    # IP-Blacklist-Fehler (gleiche Runner-IP während des ganzen Jobs)
    # hilft das zwar meist nicht, ist aber ein günstiges Sicherheitsnetz.
    last_error = None
    for attempt in range(1, 3):
        try:
            with smtplib.SMTP("asmtp.mail.hostpoint.ch", 587, timeout=20) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, recipients, msg.as_string())
            print(f"Mail gesendet an {to_addr}" + (f" (CC {cc_addr})" if cc_addr else ""))
            return
        except smtplib.SMTPException as e:
            last_error = e
            print(f"SMTP-Fehler bei Versuch {attempt}/2 an {to_addr}: {e}")
            if attempt < 2:
                time.sleep(5)

    # Alle Versuche fehlgeschlagen -> an Aufrufer weitergeben, damit dieser
    # Kanton übersprungen wird (SHA nicht gespeichert -> wird beim nächsten
    # Lauf automatisch erneut versucht), aber andere Kantone weiterlaufen.
    raise last_error


def process_immediate(kanton):
    """Gibt True zurück, wenn der SHA-Stand aktualisiert wurde (Commit nötig)."""
    kid = kanton["id"]
    geojson_path = f"data/json/{kanton['geojson_file']}"
    sha_file = f".reporting/last_processed_sha_{kid}.txt"

    geojson_sha = get_geojson_sha(geojson_path)

    last = ""
    if os.path.exists(sha_file):
        last = open(sha_file, encoding="utf-8").read().strip()

    if geojson_sha == last:
        print(f"[{kid}] bereits verarbeitet ({geojson_sha[:8]})")
        return False

    if has_changed(geojson_sha, geojson_path):
        old_tmp = f"/tmp/old_{kid}.geojson"
        show_old_version(geojson_sha, geojson_path, old_tmp)

        subprocess.run(
            ["python3", "scripts/geojson_diff.py", old_tmp, geojson_path],
            check=True,
        )

        if os.path.exists("diff.html"):
            with open("diff.html", encoding="utf-8") as f:
                html_body = f.read()

            recipient = os.environ.get(kanton["mail_recipient_secret"], "")
            cc = os.environ.get("MAIL_COPY") if kanton.get("use_cc") else None

            if recipient:
                try:
                    send_mail(
                        subject=f"Änderungen an Defis {kanton['name']}",
                        html_body=html_body,
                        to_addr=recipient,
                        cc_addr=cc,
                    )
                    time.sleep(SEND_DELAY_SECONDS)
                except Exception as e:
                    print(f"[{kid}] FEHLER beim Mailversand: {e}")
                    print(f"[{kid}] SHA wird NICHT gespeichert - wird beim "
                          f"nächsten Lauf automatisch erneut versucht.")
                    os.remove("diff.html")
                    return False
            else:
                print(f"[{kid}] WARNUNG: kein Empfänger-Secret gefunden "
                      f"({kanton['mail_recipient_secret']})")

            os.remove("diff.html")
        else:
            print(f"[{kid}] Diff-Script lief, aber keine relevanten Änderungen.")
    else:
        print(f"[{kid}] Kein inhaltlicher Diff trotz neuem SHA.")

    os.makedirs(".reporting", exist_ok=True)
    with open(sha_file, "w", encoding="utf-8") as f:
        f.write(geojson_sha)

    return True


def process_be_style(kanton):
    """BE-Stil: sofort neu/gelöscht, geändert wird separat wöchentlich versendet."""
    kid = kanton["id"]
    geojson_path = f"data/json/{kanton['geojson_file']}"
    sha_file = f".reporting/last_processed_sha_{kid}.txt"
    pending_file = f".reporting/pending_changes_{kid}.json"

    geojson_sha = get_geojson_sha(geojson_path)

    last = ""
    if os.path.exists(sha_file):
        last = open(sha_file, encoding="utf-8").read().strip()

    if geojson_sha == last:
        print(f"[{kid}] bereits verarbeitet ({geojson_sha[:8]})")
        return False

    if has_changed(geojson_sha, geojson_path):
        old_tmp = f"/tmp/old_{kid}.geojson"
        show_old_version(geojson_sha, geojson_path, old_tmp)

        subprocess.run(
            ["python3", "scripts/geojson_diff_be.py", old_tmp, geojson_path, pending_file],
            check=True,
        )

        if os.path.exists("diff_immediate.html"):
            with open("diff_immediate.html", encoding="utf-8") as f:
                html_body = f.read()

            recipient = os.environ.get(kanton["mail_recipient_secret"], "")
            cc = os.environ.get("MAIL_COPY") if kanton.get("use_cc") else None

            if recipient:
                try:
                    send_mail(
                        subject=f"Neue/gelöschte Defis – {kanton['name']}",
                        html_body=html_body,
                        to_addr=recipient,
                        cc_addr=cc,
                    )
                    time.sleep(SEND_DELAY_SECONDS)
                except Exception as e:
                    print(f"[{kid}] FEHLER beim Mailversand: {e}")
                    print(f"[{kid}] SHA wird NICHT gespeichert - wird beim "
                          f"nächsten Lauf automatisch erneut versucht.")
                    os.remove("diff_immediate.html")
                    return False
            else:
                print(f"[{kid}] WARNUNG: kein Empfänger-Secret gefunden "
                      f"({kanton['mail_recipient_secret']})")

            os.remove("diff_immediate.html")
        else:
            print(f"[{kid}] Keine sofortigen Änderungen (neu/gelöscht).")
    else:
        print(f"[{kid}] Kein inhaltlicher Diff trotz neuem SHA.")

    os.makedirs(".reporting", exist_ok=True)
    with open(sha_file, "w", encoding="utf-8") as f:
        f.write(geojson_sha)

    return True


def main():
    config = load_config()
    state_changed = False

    for kanton in config["kantone"]:
        mode = kanton.get("reporting_mode", "immediate")
        try:
            if mode == "immediate":
                changed = process_immediate(kanton)
            elif mode == "immediate_new_deleted_weekly_changed":
                changed = process_be_style(kanton)
            else:
                print(f"WARNUNG: Unbekannter reporting_mode '{mode}' für {kanton['id']}")
                changed = False
        except subprocess.CalledProcessError as e:
            print(f"FEHLER bei Kanton {kanton['id']}: {e}")
            changed = False

        state_changed = state_changed or changed

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"STATE_CHANGED={'true' if state_changed else 'false'}\n")

    print(f"\nFertig. STATE_CHANGED={state_changed}")


if __name__ == "__main__":
    main()
