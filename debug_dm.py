#!/usr/bin/env python3
"""Dump de diagnóstico: qué responde cada endpoint de Dailymotion para los ids
de Trece/Unicanal/ABC. Se corre sólo bajo demanda (workflow_dispatch debug_dm)
y escribe reportes que el workflow publica como anotaciones."""
import json
import sys

import requests

import streamlib as s

IDS = {
    "Trece-historico": "k4nLYiNrBX8W5jDbSlM",
    "Trece-live": "xak2neu",
    "Unicanal-live": "xak2lou",
    "ABC-live": "kQRS6ZAjGuMkByE4Mtc",
}
ENDPOINTS = {
    "metadata": lambda vid: "https://www.dailymotion.com/player/metadata/video/" + vid,
    "embed": lambda vid: "https://www.dailymotion.com/embed/video/" + vid,
    "api_ca97": lambda vid: "https://api.dailymotion.com/video/" + vid,
    "l1_live": lambda vid: "https://www.dailymotion.com/l1/live/get/" + vid,
}


def main():
    vid = sys.argv[1] if len(sys.argv) > 1 else "xak2neu"
    for name, mk in ENDPOINTS.items():
        url = mk(vid)
        params = {"fields": "id,hls_url,live,qualified_videos_url", "key": "ca97"} if name == "api_ca97" else {
            "stream_format": "playlist", "type": "html5", "stream_protocol": "hls"} if name == "l1_live" else {}
        try:
            r = requests.get(url, params=params, headers=s.hdr(), timeout=15)
            body = r.text[:2500]
            try:
                body = json.dumps(r.json(), indent=0)[:2500]
            except ValueError:
                pass
        except Exception as e:
            body = type(e).__name__ + ": " + str(e)[:200]
        s.report({"title": "debug-" + name + "-" + vid[:8], "url": url, "valid": False,
                  "note": body.replace("\n", " ")[:900]})
        print(name, "OK")


if __name__ == "__main__":
    main()
