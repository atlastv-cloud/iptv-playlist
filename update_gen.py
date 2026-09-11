#!/usr/bin/env python3
"""Refresca 'GEN HD'.

GEN rediseñó su home: ahora es un reproductor HTML5 genérico (botón Play y
selector de señales) — el viejo "GEN 2" ya no existe. Estrategia nueva:
  1. abrir gen.com.py con Playwright y escuchar TODA request .m3u8 (red +
     cuerpos JSON/JS del player, por si la URL viene dentro de una config);
  2. si nada aparece solo, clickear de forma tolerante (texto Play/EN VIVO,
     [class*=play], el <video>, dentro de iframes también);
  3. rankear candidatos: "gentv" > firmado (k=/exp=) > cualquier .m3u8;
  4. streamlib.update_entry() PROBEA el candidato (playlist->variante->
     segmento) y recién ahí escribe. URL no verificada no entra nunca.
"""
import re
import sys

import streamlib as s

TITLE = "GEN HD"
HOME = "https://www.gen.com.py/"
M3U8_IN_TEXT = re.compile(r"https?://[^\s\"'<>\\]+\.m3u8[^\s\"'<>\\]*")
CLICK_SELECTORS = [
    "text=/^\\s*(gen ?2|en vivo|ver en vivo|play|reproducir|mirar|ver canal)\\s*$/i",
    "button[aria-label*=play i]",
    "[class*='play' i]",
    "video",
]


def _score(u):
    sc = 0
    low = u.lower()
    if "gentv" in low:
        sc += 4
    if "k=" in u or "sec2" in u or "admin=" in u:
        sc += 2
    if "desdeparaguay" in low:
        sc += 1
    if "baja" in low:
        sc += 0.5
    return -sc


def sniff():
    found = []

    def on_request(req):
        if ".m3u8" in req.url:
            found.append(req.url)

    def on_response(resp):
        ct = (resp.headers.get("content-type") or "").lower()
        if "json" in ct or "javascript" in ct:
            try:
                found.extend(M3U8_IN_TEXT.findall(resp.text()))
            except Exception:
                pass

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("GEN: playwright no disponible — no se puede scrapear")
        return found

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        page = browser.new_page(user_agent=s.UA, viewport={"width": 1280, "height": 720})
        page.on("request", on_request)
        page.on("response", on_response)
        try:
            page.goto(HOME, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            for _attempt in range(2):
                for frame in page.frames:
                    stop = False
                    for sel in CLICK_SELECTORS:
                        try:
                            loc = frame.locator(sel)
                            n = min(loc.count(), 8)
                        except Exception:
                            continue
                        for i in range(n):
                            try:
                                loc.nth(i).click(timeout=2500, force=True)
                            except Exception:
                                continue
                            page.wait_for_timeout(1800)
                            if found:
                                stop = True
                                break
                        if stop:
                            break
                    if stop:
                        break
                if found:
                    break
                page.wait_for_timeout(2500)
            try:
                found.extend(M3U8_IN_TEXT.findall(page.content()))
            except Exception:
                pass
        except Exception as e:
            print("GEN: error de navegador:", type(e).__name__, str(e)[:140])
        finally:
            browser.close()
    return found


def main():
    uniq = list(dict.fromkeys(sniff()))
    s.report({"title": "GEN-capturas", "url": "n/a", "valid": bool(uniq),
              "note": "urls capturadas: " + str(uniq[:6])[:900]})
    if not uniq:
        print("GEN: no se capturó ningún .m3u8; playlist queda intacta")
        return 1
    print("GEN: capturadas", len(uniq), "urls:")
    for u in uniq[:8]:
        print("   -", u[:140])
    cand = sorted(uniq, key=_score)[0]
    ok, note = s.update_entry(TITLE, cand)
    print("GEN HD:", note)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
