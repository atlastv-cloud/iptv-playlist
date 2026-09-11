"""Sniffing de .m3u8 vía navegador headless para lives de Dailymotion con
restricciones de embed (el metadata API no basta, pero la propia página de
dailymotion.com/<usuario> reproduce el live sin trabas).

Retorna las URLs que el player oficial pide por red (y las que aparecen en
cuerpos JSON/JS), priorizando dailymotion.com/playlist/video/*.m3u8?auth=...
(redirect de larga vida, re-firma hacia el CDN) sobre sec2(...) (vida corta).
"""
import re

import streamlib as s

M3U8_RE = re.compile(r"\.m3u8(\?|#|$)", re.I)
FILTER = re.compile(r"(dmcdn\.net|dailymotion\.com/playlist|/live-|sec2\()", re.I)
URL_IN_TEXT = re.compile(r"https?:[^\s\"'<>\\]+\.m3u8[^\s\"'<>\\]*")


def sniff(page_url, wait_initial=8000, max_clicks=3):
    seen = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("browser_live: playwright no disponible")
        return seen

    def on_request(req):
        if M3U8_RE.search(req.url) and FILTER.search(req.url):
            seen.append(req.url)

    def on_response(resp):
        ct = (resp.headers.get("content-type") or "").lower()
        if ("json" in ct or "javascript" in ct) and resp.status and resp.status < 400:
            try:
                seen.extend(m for m in URL_IN_TEXT.findall(resp.text()) if FILTER.search(m))
            except Exception:
                pass

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        ctx = b.new_context(user_agent=s.UA, viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
        page.on("request", on_request)
        page.on("response", on_response)
        try:
            page.goto(page_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_initial)
            # banners de consentimiento de cookies (común en Py/EU) bloquean el player
            for ctext in ["text=/^\\s*(aceptar (todos|todo)?|accept( all)?|de acuerdo|同意)\\s*$/i",
                          "#didomi-notice-agree-button", ".qc-cmp2-summary-buttons button"]:
                try:
                    loc = page.locator(ctext)
                    if loc.count():
                        loc.first.click(timeout=2000)
                        page.wait_for_timeout(1500)
                except Exception:
                    pass
            tries = 0
            while not seen and tries < max_clicks:
                tries += 1
                for sel in ["[class*='play' i]", "button[aria-label*=play i]", "video"]:
                    try:
                        loc = page.locator(sel)
                        n = min(loc.count(), 4)
                    except Exception:
                        continue
                    clicked = False
                    for i in range(n):
                        try:
                            loc.nth(i).click(timeout=1500, force=True)
                        except Exception:
                            continue
                        clicked = True
                        page.wait_for_timeout(2500)
                        if seen:
                            break
                    if seen:
                        break
                    if not clicked:
                        continue
                if seen:
                    break
            try:
                seen.extend(m for m in URL_IN_TEXT.findall(page.content()) if FILTER.search(m))
            except Exception:
                pass
        except Exception as e:
            print("browser_live:", page_url, "->", type(e).__name__, str(e)[:120])
        finally:
            b.close()
    return list(dict.fromkeys(seen))


def rank(urls):
    def sc(u):
        x = 0
        if "dailymotion.com/playlist" in u:
            x -= 3          # redirect-based, la más duradera
        if "/sec2(" in u:
            x += 1          # firmada corta, última opción
        if "live" in u.lower():
            x -= 1
        return x
    return sorted(urls, key=sc)
