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

# Fehler pro Kanton. Werden am Ende in der Zusammenfassung des Workflow-Laufs
# angezeigt und machen den Lauf rot (die anderen Kantone laufen trotzdem durch).
ERRORS = []


class KantonError(Exception):
    """Fehler bei einem Kanton: reason = kurze Ursache, detail = technische Meldung."""
    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def run_script(cmd, kanton):
    """Startet ein Diff-Script. Bei Fehler: KantonError mit der letzten
    Fehlerzeile (z.B. 'ImportError: ...') statt nur 'exit status 1'."""
    result = subprocess.run(cmd, env=script_env(kanton), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        lines = [l for l in result.stderr.strip().splitlines() if l.strip()]
        last = lines[-1].strip() if lines else f"Exit-Code {result.returncode}"
        raise KantonError(f"{os.path.basename(cmd[1])} ist abgestürzt", last)

# Vergleich gegen den zuletzt verarbeiteten Stand statt nur gegen den direkten
# Vorgänger-Commit. Schliesst die Lücke bei verpassten Läufen (siehe README).
# False = bisheriges Verhalten (Vergleich sha^..sha).
COMPARE_TO_LAST_STATE = True

# Betreffzeilen pro Sprache ("language" in kantone_config.json, Standard "de")
SUBJECTS = {
    "de": {
        "immediate": "Änderungen an Defis Kanton {name}",
        "be_style": "Neue/gelöschte Defis – {name}",
    },
    "fr": {
        "immediate": "Défibrillateurs\u00a0: modifications – {name}",
        "be_style": "Défibrillateurs nouveaux/supprimés – {name}",
    },
}


def lang_of(kanton):
    lang = str(kanton.get("language", "de")).strip().lower()
    return lang if lang in SUBJECTS else "de"


def subject_for(kanton, kind):
    return SUBJECTS[lang_of(kanton)][kind].format(name=kanton["name"])


def script_env(kanton):
    """Umgebung für die Diff-Scripts: Report-Sprache mitgeben."""
    return {**os.environ, "REPORT_LANG": lang_of(kanton)}


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_geojson_sha(path):
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", path],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def diff_base(last, sha):
    """Vergleichsbasis für den Diff.

    Normalfall: der zuletzt verarbeitete Stand (last). So werden auch Änderungen
    aus Overpass-Commits erfasst, die zwischen zwei erfolgreichen Läufen lagen
    (z.B. nach einem fehlgeschlagenen Mailversand). Liegt nur ein Commit
    dazwischen, ist das Ergebnis identisch mit dem früheren Vergleich sha^..sha.

    Fallback: der direkte Vorgänger (sha^), falls kein gültiger Stand vorliegt
    oder COMPARE_TO_LAST_STATE ausgeschaltet ist.
    """
    if last and COMPARE_TO_LAST_STATE:
        is_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", last, sha],
            capture_output=True,
        ).returncode == 0
        if is_ancestor:
            return last
        print(f"Hinweis: gespeicherter Stand {last[:8]} ist kein Vorgänger von "
              f"{sha[:8]} - verwende {sha[:8]}^ als Vergleichsbasis.")
    return f"{sha}^"


def exists_at(base, path):
    return subprocess.run(["git", "cat-file", "-e", f"{base}:{path}"],
                          capture_output=True).returncode == 0


def has_changed(base, sha, path):
    result = subprocess.run(["git", "diff", "--quiet", f"{base}..{sha}", "--", path])
    return result.returncode != 0


def show_old_version(base, path, out_path):
    with open(out_path, "wb") as f:
        subprocess.run(["git", "show", f"{base}:{path}"], stdout=f, check=True)


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

    if not last:
        # Noch nie verarbeitet (neu aufgenommener Kanton): nur initialisieren.
        # Sonst bekäme der Empfänger als erste Mail eine beliebig alte Änderung.
        print(f"[{kid}] Initialisiert auf {geojson_sha[:8]} (neu im Reporting, kein Report).")
        os.makedirs(".reporting", exist_ok=True)
        with open(sha_file, "w", encoding="utf-8") as f:
            f.write(geojson_sha)
        return True

    base = diff_base(last, geojson_sha)
    if not exists_at(base, geojson_path):
        # Datei existierte beim Vergleichsstand noch nicht (neuer Kanton):
        # nur initialisieren, sonst käme der ganze Bestand als "neu".
        print(f"[{kid}] Initialisiert auf {geojson_sha[:8]} (Datei neu, kein Report).")
        os.makedirs(".reporting", exist_ok=True)
        with open(sha_file, "w", encoding="utf-8") as f:
            f.write(geojson_sha)
        return True

    if has_changed(base, geojson_sha, geojson_path):
        old_tmp = f"/tmp/old_{kid}.geojson"
        show_old_version(base, geojson_path, old_tmp)

        run_script(["python3", "scripts/geojson_diff.py", old_tmp, geojson_path], kanton)

        if os.path.exists("diff.html"):
            with open("diff.html", encoding="utf-8") as f:
                html_body = f.read()

            recipient = os.environ.get(kanton["mail_recipient_secret"], "")
            cc = os.environ.get("MAIL_COPY") if kanton.get("use_cc") else None

            if recipient:
                try:
                    send_mail(
                        subject=subject_for(kanton, "immediate"),
                        html_body=html_body,
                        to_addr=recipient,
                        cc_addr=cc,
                    )
                    time.sleep(SEND_DELAY_SECONDS)
                except Exception as e:
                    os.remove("diff.html")
                    raise KantonError("Mailversand fehlgeschlagen", str(e))
            else:
                os.remove("diff.html")
                raise KantonError(
                    "Kein Empfänger: Secret fehlt oder ist nicht im Workflow eingetragen",
                    kanton["mail_recipient_secret"])

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

    if not last:
        # Noch nie verarbeitet (neu aufgenommener Kanton): nur initialisieren.
        # Sonst bekäme der Empfänger als erste Mail eine beliebig alte Änderung.
        print(f"[{kid}] Initialisiert auf {geojson_sha[:8]} (neu im Reporting, kein Report).")
        os.makedirs(".reporting", exist_ok=True)
        with open(sha_file, "w", encoding="utf-8") as f:
            f.write(geojson_sha)
        return True

    base = diff_base(last, geojson_sha)
    if not exists_at(base, geojson_path):
        # Datei existierte beim Vergleichsstand noch nicht (neuer Kanton):
        # nur initialisieren, sonst käme der ganze Bestand als "neu".
        print(f"[{kid}] Initialisiert auf {geojson_sha[:8]} (Datei neu, kein Report).")
        os.makedirs(".reporting", exist_ok=True)
        with open(sha_file, "w", encoding="utf-8") as f:
            f.write(geojson_sha)
        return True

    if has_changed(base, geojson_sha, geojson_path):
        old_tmp = f"/tmp/old_{kid}.geojson"
        show_old_version(base, geojson_path, old_tmp)

        run_script(["python3", "scripts/geojson_diff_be.py", old_tmp, geojson_path,
                    pending_file], kanton)

        if os.path.exists("diff_immediate.html"):
            with open("diff_immediate.html", encoding="utf-8") as f:
                html_body = f.read()

            recipient = os.environ.get(kanton["mail_recipient_secret"], "")
            cc = os.environ.get("MAIL_COPY") if kanton.get("use_cc") else None

            if recipient:
                try:
                    send_mail(
                        subject=subject_for(kanton, "be_style"),
                        html_body=html_body,
                        to_addr=recipient,
                        cc_addr=cc,
                    )
                    time.sleep(SEND_DELAY_SECONDS)
                except Exception as e:
                    os.remove("diff_immediate.html")
                    raise KantonError("Mailversand fehlgeschlagen", str(e))
            else:
                os.remove("diff_immediate.html")
                raise KantonError(
                    "Kein Empfänger: Secret fehlt oder ist nicht im Workflow eingetragen",
                    kanton["mail_recipient_secret"])

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
        except KantonError as e:
            ERRORS.append((kanton, e.reason, e.detail))
            changed = False
        except Exception as e:
            # Unerwarteter Fehler: nur diesen Kanton überspringen.
            ERRORS.append((kanton, "Unerwarteter Fehler", f"{type(e).__name__}: {e}"))
            changed = False

        state_changed = state_changed or changed

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"STATE_CHANGED={'true' if state_changed else 'false'}\n")
            f.write(f"REPORTING_ERRORS={len(ERRORS)}\n")

    report_errors()
    print(f"\nFertig. STATE_CHANGED={state_changed}, Fehler: {len(ERRORS)}")


def report_errors():
    """Fehler sichtbar machen: als Annotation und als Tabelle auf der
    Übersichtsseite des Workflow-Laufs (Job Summary)."""
    if not ERRORS:
        return
    print("\n=== FEHLER ===")
    for kanton, reason, detail in ERRORS:
        msg = f"{reason}: {detail}" if detail else reason
        print(f"[{kanton['id']}] {msg}")
        print(f"::error title=Kanton {kanton['name']}::{msg} "
              f"(Stand nicht gespeichert, nächster Lauf versucht es erneut)")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## ⚠️ Reporting-Fehler\n\n")
            f.write("Diese Kantone haben in diesem Lauf **keine Mail** bekommen. "
                    "Ihr Stand wurde nicht gespeichert, der nächste Lauf versucht "
                    "es automatisch erneut.\n\n")
            f.write("| Kanton | Ursache | Details |\n|---|---|---|\n")
            for kanton, reason, detail in ERRORS:
                d = (detail or "").replace("|", "\\|").replace("\n", " ")
                f.write(f"| {kanton['name']} ({kanton['id']}) | {reason} | `{d}` |\n")


if __name__ == "__main__":
    main()
