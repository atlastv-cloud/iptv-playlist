#!/usr/bin/env python3
"""Refresca 'Unicanal HD' desde Dailymotion (igual que update_trece.py)."""
import sys

import streamlib as s

TITLE = "Unicanal HD"
EMBED_REFERER = "https://www.unicanal.com.py/"  # DM valida el referer del sitio que embebe
VIDEO_IDS = ["k1mHLKycOlKgo3Db5GI", "xak2lou"]  # id histórico + id del path del stream


def main():
    fails = []
    for vid in VIDEO_IDS:
        url, why = s.dailymotion_auto_url(vid, referer=EMBED_REFERER)
        if not url:
            print("Unicanal: vid", vid, "falló:", why)
            fails.append(vid + ": " + why)
            continue
        ok, note = s.update_entry(TITLE, url)
        print("Unicanal:", note, "(via", why + ")")
        return 0 if ok else 1
    s.report({"title": TITLE, "url": "n/a", "valid": False, "applied": False,
              "note": "DM agotado: " + " || ".join(fails)[:700]})
    return 1


if __name__ == "__main__":
    sys.exit(main())
