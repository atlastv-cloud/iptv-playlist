#!/usr/bin/env python3
"""Refresca 'Trece': saca la URL HLS firmada (sec2, expira) del metadata API de
Dailymotion para la señal en vivo del canal y la escribe en la playlist SI pasa
la validación. Si falla, deja la playlist intacta (no publica basura)."""
import sys

import streamlib as s

TITLE = "Trece"
VIDEO_IDS = ["k4nLYiNrBX8W5jDbSlM", "xak2neu"]  # id histórico + id del path del stream


def main():
    for vid in VIDEO_IDS:
        url, why = s.dailymotion_auto_url(vid)
        if not url:
            print("Trece: metadata", vid, "falló:", why)
            continue
        ok, note = s.update_entry(TITLE, url)
        print("Trece:", note)
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
