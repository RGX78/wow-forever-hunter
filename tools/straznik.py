#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Straznik sciagi huntera (WoW: Forever) — deterministyczna kontrola raportu robota VPS.

Co sprawdza:
 1. licznik wpisow RAPORTY.md vs "delivered" w raporty_state.json
 2. index.html == sciaga-hunter.html
 3. date w sciadze vs data najnowszego wpisu (nie moze byc starsza)
 4. build bety wspomniany w raporcie musi byc w sciadze
 5. sprzeczne zdania w sciadze (np. "Beta is over" + "Beta ends today")
 6. twierdzenia w czasie przeszlym ("is over"/"ended") przy godzinie, ktora jeszcze nie minela
 7. kluczowe byty z raportu (bez pulapek "checked but NOT added") musza byc w sciadze
 8. live == lokalny (HTTP 200) — tylko ostrzezenie, build Pages bywa w toku

Kod wyjscia: 0 = czysto (moga byc ostrzezenia), 1 = ALERTY.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(r"F:\HERMES_ORION\projects\wow-forever-hunter")
STATE = Path(r"F:\HERMES_ORION\.tmp\wow_hunter\raporty_state.json")
LOG = Path(r"F:\HERMES_ORION\.tmp\wow_hunter\straznik_log.txt")
URL = "https://rgx78.github.io/wow-forever-hunter/"

ENTITIES = [
    "Onyxia", "Drakefire", "Barrow Deeps", "Hyjal Summit", "Azuregos", "Kazzak",
    "Questie", "Hardcore", "Roleplay", "Normal", "PvP", "name reservation",
    "November 4", "Nov 4", "Raid Overview", "Fishing Contest",
]

TIME_ZONES = {"CEST": 2, "CET": 1, "PDT": -7, "PST": -8, "UTC": 0, "GMT": 0}


def norm(text):
    return text.replace("&nbsp;", " ").replace("\xa0", " ")


def origin_sheet(repo):
    """Tresc index.html z origin/master (None, gdy git niedostepny)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "show", "origin/master:index.html"],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace")
        if out.returncode == 0 and out.stdout:
            return norm(out.stdout)
    except Exception:
        pass
    return None


def parse_entries(md):
    parts = re.split(r"^## ", md, flags=re.M)
    entries = []
    for p in parts[1:]:
        lines = p.splitlines()
        head = lines[0].strip()
        entries.append({"head": head, "body": "\n".join(lines[1:])})
    return entries


def report_date(head):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", head)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def sheet_dates(html):
    out = []
    for d, mo, y in re.findall(r"(\d{1,2})\.(\d{1,2})\.(20\d\d)", html):
        try:
            out.append(dt.date(int(y), int(mo), int(d)))
        except ValueError:
            pass
    return out


def claims_of(entry):
    """Bulki, ktore twierdza ze cos WESZLO do sciagi (bez 'checked but not added')."""
    keep = []
    for line in entry["body"].splitlines():
        low = line.lower()
        if not line.strip().startswith("-"):
            continue
        if any(skip in low for skip in ("not added", "not in the sheet", "already in the sheet",
                                        "already handled", "skipped", "brak ", "not because")):
            continue
        keep.append(line)
    return keep


def check(args):
    alerts, warns, notes = [], [], []

    md_path = args.repo / "RAPORTY.md"
    sheet_path = Path(args.sheet) if args.sheet else (args.repo / "sciaga-hunter.html")
    idx_path = args.repo / "index.html"
    for p in (md_path, sheet_path):
        if not p.exists():
            alerts.append(f"brak pliku {p}")
            return alerts, warns, notes

    md = md_path.read_text(encoding="utf-8", errors="replace")
    html = norm(sheet_path.read_text(encoding="utf-8", errors="replace"))
    low = html.lower()
    entries = parse_entries(md)
    if not entries:
        alerts.append("RAPORTY.md: zero wpisow")
        return alerts, warns, notes

    # 1) licznik vs relay
    delivered = None
    if STATE.exists():
        try:
            delivered = json.loads(STATE.read_text(encoding="utf-8")).get("delivered")
        except Exception:
            warns.append("nie da sie odczytac raporty_state.json")
    notes.append(f"wpisy w RAPORTY.md: {len(entries)}, delivered: {delivered}")
    if delivered is not None and delivered != len(entries):
        alerts.append(f"relay rozjechany: RAPORTY.md={len(entries)} vs delivered={delivered}")

    # 2) index == sciaga
    if args.sheet:
        pass  # tryb testowy: porownanie z index.html nie ma sensu
    elif idx_path.exists():
        a = sheet_path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
        b = idx_path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
        if a != b:
            alerts.append("index.html != sciaga-hunter.html (strona live pokazuje inna tresc)")
    else:
        alerts.append("brak index.html")

    last = entries[-1]
    rdate = report_date(last["head"])
    notes.append(f"najnowszy wpis: {last['head']}")

    # 3) data w sciadze — bierzemy najnowsza date, ktora juz nastapila
    #    (daty w przyszlosci to zapowiedzi, np. release 4.11.2026 — nie sa znacznikiem aktualizacji)
    today = dt.datetime.now(dt.timezone.utc).date()
    dates = [d for d in sheet_dates(html) if d <= today]
    if not dates:
        alerts.append("w sciadze nie ma zadnej daty DD.MM.YYYY z przeszlosci")
    elif rdate:
        newest_sheet = max(dates)
        if newest_sheet < rdate:
            alerts.append(f"sciaga ma date {newest_sheet.strftime('%d.%m.%Y')}, "
                          f"a najnowszy raport jest z {rdate.strftime('%d.%m.%Y')} — robot nie zapisal zmian")
        notes.append(f"data w sciadze: {newest_sheet.strftime('%d.%m.%Y')}")

    # 4) build number
    builds = set(re.findall(r"1\.60\.\d+\.\d+", last["body"]))
    for b in sorted(builds):
        short = b.split(".")[-1]
        if b not in html and short not in html:
            alerts.append(f"raport podaje build {b}, ktorego nie ma w sciadze")

    # 5) sprzecznosci
    pairs = [
        ("Beta is over", "will return shortly"),
        ("Beta is over", "Beta ends today"),
        ("Beta is over", "is back online"),
        ("Beta is over", "did not come back"),
    ]
    for a, b in pairs:
        if a.lower() in low and b.lower() in low:
            alerts.append(f'sprzeczne zdania w sciadze: "{a}" obok "{b}"')

    # 6) czas przeszly vs godzina w przyszlosci — tylko w notkach mowiacych o DZISIAJ
    #    (godzina z notki o wczorajszym restarcie nie ma znaczenia)
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_marks = ("today", today.strftime("%d.%m.%Y").lstrip("0"),
                   f"{today.day} october" if today.month == 10 else "")
    blocks = re.split(r"<p", html)
    for block in blocks:
        block_low = block.lower()
        if not any(t and t in block_low for t in today_marks):
            continue
        hits = re.findall(r"(\d{1,2}):(\d{2})\s*(CEST|CET|PDT|PST|UTC|GMT)", block)
        for hh, mm, tzname in hits:
            off = TIME_ZONES.get(tzname)
            if off is None:
                continue
            when = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) \
                + dt.timedelta(hours=int(hh) - off, minutes=int(mm))
            if when <= now_utc:
                continue
            for phrase in ("beta is over", "beta has ended", "no beta client", "beta ended"):
                if phrase in block_low:
                    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", block))[:90]
                    warns.append(f'"{phrase}" przy godzinie {hh}:{mm} {tzname}, ktora jeszcze nie minela '
                                 f"(teraz {now_utc.strftime('%H:%M')} UTC) — notka moze wyprzedzac fakt: "
                                 f"„{snippet.strip()}…”")
                    break

    # 7) byty z raportu (pomijajac 'checked but not added')
    claims = claims_of(last)
    checked = " ".join(claims).lower()
    for ent in ENTITIES:
        if ent.lower() in checked and ent.lower() not in low:
            warns.append(f'raport twierdzi, ze dodal "{ent}", ale nie ma go w sciadze')

    # 8) live vs lokalny
    if not args.no_live:
        try:
            req = urllib.request.Request(URL + f"?cb={dt.datetime.now().timestamp()}",
                                         headers={"User-Agent": "straznik/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                code = r.status
                remote = norm(r.read().decode("utf-8", errors="replace"))
            if code != 200:
                warns.append(f"live HTTP {code}")
            else:
                ref = origin_sheet(args.repo)
                base = ref if ref is not None else html
                label = "origin" if ref is not None else "lokalny"
                if remote.replace("\r", "") != base.replace("\r", ""):
                    warns.append(f"live != {label} (build Pages w toku albo brak pusha — sprawdz za ~2 min)")
                else:
                    notes.append(f"live == {label} ✓")
                    if ref is not None and html.replace("\r", "") != ref.replace("\r", ""):
                        warns.append("lokalne repo niezsynchronizowane z origin — zrob git pull/merge "
                                     "(live jest OK, to tylko kopia na PC jest stara)")
        except Exception as exc:
            warns.append(f"nie moge sprawdzic live: {exc}")
    return alerts, warns, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--sheet", default=None, help="podmien plik sciagi (test)")
    ap.add_argument("--no-live", action="store_true")
    args = ap.parse_args()
    args.repo = Path(args.repo)

    alerts, warns, notes = check(args)

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== Straznik sciagi — {stamp} ===")
    for n in notes:
        print(f"  . {n}")
    for w in warns:
        print(f"  ! OSTRZEZENIE: {w}")
    for a in alerts:
        print(f"  X ALERT: {a}")
    verdict = "ALERTY" if alerts else ("OK z ostrzezeniami" if warns else "OK")
    print(f"WERDYKT: {verdict}")

    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} | {verdict} | alerts={len(alerts)} warns={len(warns)} | "
                    f"{'; '.join(alerts + warns) or '-'}\n")
    except Exception:
        pass

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
