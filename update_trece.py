#!/usr/bin/env python3
"""Refresca 'Trece' desde Dailymotion (metadata -> embed -> api). Valida con
probe antes de escribir; deja reporte incluso si falla (anotación en Actions)."""
import sys

import streamlib as s

TITLE = "Trece"
VIDEO_IDS = ["k4nLYiNrBX8W5jDbSlM", "xak2neu"]  # id histórico + id del path del stream


def main():
    fails = []
    for vid in VIDEO_IDS:
        url, why = s.dailymotion_auto_url(vid)
        if not url:
            print("Trece: vid", vid, "falló:", why)
            fails.append(vid + ": " + why)
            continue
        ok, note = s.update_entry(TITLE, url)
        print("Trece:", note, "(via", why + ")")
        return 0 if ok else 1
    s.report({"title": TITLE, "url": "n/a", "valid": False, "applied": False,
              "note": "DM agotado: " + " || ".join(fails)[:700]})
    return 1


if __name__ == "__main__":
    sys.exit(main())
