#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orion — dzienny zbieracz informacji o WoW: Forever (dla huntera) — v2.
Zmiana v2: oprocz pelnego raportu zapisuje DELTA (tylko sekcje zmienione vs poprzedni dzien),
naprawiona lista zrodel (usuniete martwe adresy, dodane strony z nowosciami).
Wynik: F:\HERMES_ORION\.tmp\wow_hunter_daily\<data>.txt + <data>_delta.txt
Czysty Python (stdlib). Nie wymaga AI.
"""
import json
import os
import re
import ssl
import io
import glob
import datetime
import urllib.request

OUT_DIR = os.environ.get("WOW_SCOUT_OUT", r"F:\HERMES_ORION\.tmp\wow_hunter_daily")
TIMEOUT = 15
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OrionAgent/1.0"

SOURCES = [
    # --- oficjalne ---
    ("https://worldofwarcraft.blizzard.com/en-us/news", "Blizzard news (WoW)"),
    ("https://news.blizzard.com/en-us/world-of-warcraft", "Blizzard news blog"),
    # --- nowosci / patche ---
    ("https://www.stillsixty.com/news", "stillsixty — News (patch notes, blue tracker)"),
    ("https://theforeverera.com/en/news/", "Forever Era — News"),
    ("https://wow-forever.gg/news/", "wow-forever.gg — News"),
    ("https://wowforeverbuilds.com/news", "wowforeverbuilds — News"),
    ("https://www.wowhead.com/forever/news", "Wowhead Forever news"),
    ("https://www.wowhead.com/forever/blue-tracker", "Blue tracker Forever"),
    ("https://wowclassicforever.info/patch-notes/", "Patch notes (wowclassicforever)"),
    ("https://wow-forever.online/", "wow-forever.online"),
    # --- poradniki huntera ---
    ("https://www.stillsixty.com/leveling/hunter", "stillsixty Hunter 1-60"),
    ("https://theforeverera.com/en/guides/classes/hunter/", "Forever Era Hunter"),
    ("https://wow-forever.gg/guides/classes/hunter/", "wow-forever.gg Hunter"),
    ("https://wowforeverbuilds.com/classes/hunter", "wowforeverbuilds Hunter"),
    ("https://wowclassicforever.info/classes/hunter/", "wowclassicforever Hunter"),
    ("https://wowf.io/en/leveling/hunter/beast-mastery", "wowf.io BM leveling"),
    ("https://wowforeversite.wiki/classes/hunter", "wowforeversite Hunter"),
]

GITHUB = [
    ("Questie/Questie", "Questie (commity — nowe questy Forever)"),
    ("Gethe/wow-ui-source", "wow-ui-source (gałąź forever)"),
]

SECTION_RE = re.compile(r"(?m)^########## ")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def strip_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", html)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&hellip;", "...").replace("&mdash;", "—"))
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def clip(txt, n=9000):
    return txt if len(txt) <= n else txt[:n] + "\n... [uciete]"


def split_sections(text):
    """Zwraca (dict tytul->tresc, lista tytulow w kolejnosci)."""
    parts = SECTION_RE.split(text)
    secs, order = {}, []
    for p in parts[1:]:
        title = p.split("\n", 1)[0].strip()
        secs[title] = p.strip()
        order.append(title)
    return secs, order


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def find_previous(today_file):
    files = sorted(glob.glob(os.path.join(OUT_DIR, "*.txt")))
    prev = None
    for f in files:
        b = os.path.basename(f)
        if "_delta" in b:
            continue
        if b == os.path.basename(today_file):
            continue
        prev = f
    return prev


def write_delta(today, out_path, prev_text=None, prev_src=None):
    delta_path = os.path.join(OUT_DIR, today + "_delta.txt")
    cur_secs, cur_order = split_sections(io.open(out_path, encoding="utf-8").read())
    lines = ["=== DELTA %s ===" % today]
    if prev_src:
        lines.append("[Porownano z: %s]" % prev_src)
    changed = []
    if prev_text is None:
        lines.append("[BASELINE — brak poprzedniego raportu. Sekcje: %s]" % ", ".join(cur_order))
        lines.append("[Nic nie dodawaj na podstawie baseline — to tylko pierwszy dzien.]")
    else:
        prev_secs, _ = split_sections(prev_text)
        for t in cur_order:
            if t not in prev_secs or norm(prev_secs[t]) != norm(cur_secs[t]):
                changed.append(t)
        if not changed:
            lines.append("[NO-CHANGE — zaden zrodlowy nie zmienil sie istotnie]")
        else:
            lines.append("[ZMIANY w %d sekcjach]" % len(changed))
        unchanged = [t for t in cur_order if t not in changed]
        lines.append("[Bez zmian: %s]" % (", ".join(unchanged) if unchanged else "brak"))
    for t in changed:
        body = cur_secs[t]
        if len(body) > 6000:
            body = body[:6000] + "\n... [obciete do 6000 znakow]"
        lines.append("\n########## " + body)
    io.open(delta_path, "w", encoding="utf-8").write("\n".join(lines))
    return delta_path, len(changed)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    out_path = os.path.join(OUT_DIR, today + ".txt")
    ok, fail = [], []

    # v3: porownuj z POPRZEDNIM PRZEBIEGIEM (nie z poprzednim dniem) — dziala tez przy kilku przebiegach dziennie
    prev_text, prev_src = None, None
    if os.path.exists(out_path):
        prev_text = io.open(out_path, encoding="utf-8").read()
        prev_src = "poprzedni przebieg (ten sam plik, wczesniej dzisiaj)"
    else:
        prev_path = find_previous(out_path)
        if prev_path:
            prev_text = io.open(prev_path, encoding="utf-8").read()
            prev_src = os.path.basename(prev_path)

    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write("=== ZBIORCZY RAPORT WoW Forever — %s ===\n\n" % today)

        for url, label in SOURCES:
            try:
                txt = clip(strip_html(fetch(url)))
                f.write("\n########## %s\nURL: %s\n%s\n" % (label, url, txt))
                ok.append(label)
            except Exception as e:
                f.write("\n########## %s\nURL: %s\n[BLAD: %s]\n" % (label, url, e))
                fail.append("%s (%s)" % (label, e))

        for repo, label in GITHUB:
            try:
                j = json.loads(fetch("https://api.github.com/repos/%s/commits?per_page=8" % repo))
                f.write("\n########## %s\nURL: https://github.com/%s/commits\n" % (label, repo))
                for c in j:
                    msg = (c.get("commit", {}).get("message", "") or "").split("\n")[0]
                    date = c.get("commit", {}).get("committer", {}).get("date", "")
                    f.write("* %s  %s\n" % (date[:10], msg))
                ok.append(label)
            except Exception as e:
                f.write("\n########## %s\n[BLAD: %s]\n" % (label, e))
                fail.append("%s (%s)" % (label, e))

        f.write("\n\n=== PODSUMOWANIE ZBIORU ===\n")
        f.write("OK (%d): %s\n" % (len(ok), ", ".join(ok)))
        f.write("BLEDY (%d): %s\n" % (len(fail), ", ".join(fail) or "brak"))

    delta_path, n_changed = write_delta(today, out_path, prev_text, prev_src)
    print("pelny raport: %s" % out_path)
    print("delta: %s  (zmienionych sekcji: %d)" % (delta_path, n_changed))
    print("OK=%d  BLEDY=%d" % (len(ok), len(fail)))


if __name__ == "__main__":
    main()
