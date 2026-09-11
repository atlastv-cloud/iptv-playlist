#!/usr/bin/env python3
"""Refresca 'ABC TV'.

ABC transmite en Dailymotion; su página (abc.com.py/tv) embebe el player con el
video-id actual. Hacer matcheo del id desde la página hace que el updater
sobreviva si ABC rota de id. Fallback: id conocido (x9skr3m). Obtener la URL
firmada via la cadena metadata->embed->api de streamlib.
"""
import re
import sys

import requests

import streamlib as s

TITLE = "ABC TV"
PAGE = "https://www.abc.com.py/tv/"
FALLBACK_IDS = ["x9skr3m"]
ID_RE = re.compile(r"(?:embed/video/|dailymotion\.com/(?:video|player/metadata/video)/|player\.html\?video=|video=)([xk][0-9A-Za-z]{5,24})")


def page_ids():
    """Ids de Dailymotion embebidos en la página oficial de ABC TV."""
    try:
        r = requests.get(PAGE, headers=s.hdr("https://www.abc.com.py/"),
                         timeout=15, verify=False)
        if r.status_code != 200:
            return [], "página HTTP " + str(r.status_code)
        found = []
        for m in ID_RE.finditer(r.text):
            vid = m.group(1)
            if vid not in found:
                found.append(vid)
        return found, "ok"
    except Exception as e:
        return [], type(e).__name__ + ": " + str(e)[:110]


def main():
    scraped, why = page_ids()
    print("ABC TV: ids en abc.com.py/tv =", scraped or "[]", "(" + why + ")")
    s.report({"title": "ABC-pagina", "url": PAGE, "valid": bool(scraped),
              "note": "ids scraping=" + str(scraped[:5]) + " (" + why + ")"})
    tried, fails = [], []
    for vid in scraped + FALLBACK_IDS:
        if vid in tried:
            continue
        tried.append(vid)
        url, w = s.dailymotion_auto_url(vid, referer=PAGE)
        if not url:
            print("ABC TV: vid", vid, "falló:", w)
            fails.append(vid + ": " + w)
            continue
        ok, note = s.update_entry(TITLE, url)
        print("ABC TV:", note, "(via", w + ")")
        return 0 if ok else 1
    s.report({"title": TITLE, "url": "n/a", "valid": False, "applied": False,
              "note": "DM agotado: " + " || ".join(fails)[:700]})
    return 1


if __name__ == "__main__":
    sys.exit(main())
