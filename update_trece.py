#!/usr/bin/env python3
"""Refresca 'Trece' desde Dailymotion (metadata -> embed -> api). Valida con
probe antes de escribir; deja reporte incluso si falla (anotación en Actions)."""
import sys

import streamlib as s

TITLE = "Trece"
EMBED_REFERER = "https://www.trece.com.py/en-vivo/"  # DM valida el referer del sitio que embebe
DM_PAGES = ["https://www.dailymotion.com/trecepy",
              "https://www.dailymotion.com/embed/video/k4nLYiNrBX8W5jDbSlM?autoplay=true&mute=true",
              "https://www.trece.com.py/en-vivo/"]
VIDEO_IDS = ["k4nLYiNrBX8W5jDbSlM", "xak2neu"]  # id histórico + id del path del stream


def main():
    fails = []
    for vid in VIDEO_IDS:
        url, why = s.dailymotion_auto_url(vid, referer=EMBED_REFERER)
        if not url:
            print("Trece: vid", vid, "falló:", why)
            fails.append(vid + ": " + why)
            continue
        ok, note = s.update_entry(TITLE, url)
        print("Trece:", note, "(via", why + ")")
        return 0 if ok else 1
    ok, note = s.browser_fallback(TITLE, DM_PAGES)
    print(TITLE, "(browser fallback):", note)
    if ok:
        return 0
    s.report({"title": TITLE, "url": "n/a", "valid": False, "applied": False,
              "note": "DM agotado: " + " || ".join(fails)[:400] + " || browser: " + note[:200]})
    return 1


if __name__ == "__main__":
    sys.exit(main())
