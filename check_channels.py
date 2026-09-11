#!/usr/bin/env python3
"""
check_channels.py — Verificador de salud de la playlist IPTV.

Parsea AtlasTVPilar.m3u y por cada canal:
  1. GET de la playlist (status HTTP, contenido tipo HLS, TLS laxo para evitar
     falsos negativos por certs autofirmados).
  2. Si es master playlist, baja la primera variante.
  3. Descarga los primeros ~128 KB del primer segmento .ts -> "recibe señal" real.

Salidas:
  - stdout: resumen legible (guardado en channel_check_report.log)
  - channel_status.json : resultados máquina-legibles
  - channel_status.md   : tabla Markdown
"""
import json
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

warnings.filterwarnings("ignore")  # InsecureRequestWarning, etc.
import requests  # noqa: E402

try:
    requests.packages.urllib3.disable_warnings()  # type: ignore
except Exception:
    pass

PLAYLIST_FILE = sys.argv[1] if len(sys.argv) > 1 else "AtlasTVPilar.m3u"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 14
WORKERS = 10
SEG_BYTES = 131072


# ---------- parseo ----------

def parse_m3u(path):
    """Extrae [(name, group, url, referrer), ...] respetando EXTVLCOPT."""
    with open(path, encoding="utf-8-sig") as fh:
        lines = [l.strip() for l in fh]
    chans, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#EXTINF:"):
            attrs, _, name = ln.partition(",")
            name = name.strip() or "(sin nombre)"
            meta = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
            referrer, url, j = None, None, i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith("#EXTVLCOPT:"):
                    m = re.search(r"http-referrer=(\S+)", nxt)
                    if m:
                        referrer = m.group(1)
                    j += 1
                    continue
                if nxt.startswith("#"):
                    j += 1
                    continue
                url = nxt
                break
            chans.append({"idx": len(chans) + 1, "name": name,
                          "group": meta.get("group-title", ""),
                          "url": url, "referrer": referrer})
            i = j
        i += 1
    return chans


# ---------- helpers ----------

def _headers(referrer):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if referrer:
        h["Referer"] = referrer
        p = urlparse(referrer)
        h["Origin"] = f"{p.scheme}://{p.netloc}"
    return h


def _is_hls(text):
    t = text.lstrip("\ufeff \r\n")
    return t.startswith("#EXTM3U") or "#EXTINF" in t[:4000]


def _expired_token(url):
    """Detecta expiración por query exp=<epoch> o tokens sec2(...) de DM."""
    q = parse_qs(urlparse(url).query)
    if "exp" in q:
        try:
            exp = int(float(q["exp"][0]))
            if exp < time.time():
                return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _extract(text, pat):
    m = re.search(pat, text)
    return int(m.group(1)) if m else None


def _first_uri(text, base_url):
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            return urljoin(base_url, s)
    return None


# ---------- probe ----------

def probe(ch):
    r = {**ch, "code": None, "verdict": "DEAD", "note": "", "live": None,
         "targetdur": None, "segs": None, "msize": None, "msize2": None,
         "bytes": 0, "elapsed": None, "expired": _expired_token(ch["url"] or "")}
    if not ch["url"] or not ch["url"].lower().startswith(("http://", "https://")):
        r["note"] = "no-URL (stub)"
        return r
    t0 = time.time()
    hdrs = _headers(ch["referrer"])
    try:
        resp = requests.get(ch["url"], headers=hdrs, timeout=TIMEOUT,
                            verify=False, allow_redirects=True)
        r["code"] = resp.status_code
        if resp.status_code != 200:
            r["note"] = f"HTTP {resp.status_code}"
            if r["expired"]:
                r["note"] += f" (token vencido desde {r['expired']})"
            return r
        text = resp.text
        if not _is_hls(text):
            ct = resp.headers.get("content-type", "?")
            r["note"] = f"200 pero NO es HLS (content-type: {ct})"
            return r
        if "#EXT-X-STREAM-INF" in text:  # master -> primera variante
            uri = None
            lines = text.splitlines()
            for k, ln in enumerate(lines):
                if ln.startswith("#EXT-X-STREAM-INF"):
                    for l2 in lines[k + 1:]:
                        s2 = l2.strip()
                        if s2 and not s2.startswith("#"):
                            uri = urljoin(resp.url, s2)
                            break
                    break
            if not uri:
                r["note"] = "master sin variantes"
                return r
            resp = requests.get(uri, headers=hdrs, timeout=TIMEOUT, verify=False)
            r["code"] = resp.status_code
            if resp.status_code != 200:
                r["note"] = f"variante HTTP {resp.status_code}"
                return r
            text = resp.text
        r["live"] = "#EXT-X-ENDLIST" not in text
        r["targetdur"] = _extract(text, r"#EXT-X-TARGETDURATION:(\d+)")
        segs = [l.strip() for l in text.splitlines()
                if l.strip() and not l.strip().startswith("#")]
        r["segs"] = len(segs)
        if not segs:
            r["note"] = "playlist sin segmentos"
            return r
        # profundidad 2 (nested playlist, p.ej. qaotic)
        if segs[0].lower().endswith((".m3u8", ".m3u")):
            resp = requests.get(urljoin(resp.url, segs[0]), headers=hdrs,
                                 timeout=TIMEOUT, verify=False)
            if resp.status_code != 200:
                r["note"] = f"sub-playlist HTTP {resp.status_code}"
                return r
            text = resp.text
            r["live"] = "#EXT-X-ENDLIST" not in text
            r["targetdur"] = r["targetdur"] or _extract(text, r"#EXT-X-TARGETDURATION:(\d+)")
            segs = [l.strip() for l in text.splitlines()
                    if l.strip() and not l.strip().startswith("#")]
            if not segs:
                r["note"] = "sub-playlist sin segmentos"
                return r
        # primer segmento: evidencia real de señal
        seg_url = urljoin(resp.url, segs[0])
        # si el segmento no está en el mismo host, re-probea para respetar
        # cookies/sesiones de DM etc.
        if urlparse(seg_url).netloc != urlparse(resp.url).netloc:
            requests.get(seg_url, headers=hdrs, timeout=TIMEOUT, verify=False)
        with requests.get(seg_url, headers=hdrs, timeout=TIMEOUT,
                          verify=False, stream=True) as sr:
            if sr.status_code != 200:
                r["verdict"] = "PARTIAL"
                r["note"] = f"playlist OK pero segmento HTTP {sr.status_code}"
                return r
            n = 0
            for chunk in sr.iter_content(16384):
                n += len(chunk)
                r["bytes"] = n
                if n >= SEG_BYTES:
                    break
        if n < 2048:
            r["verdict"] = "PARTIAL"
            r["note"] = f"segmento vacío/truncado ({n} B)"
            return r
        r["verdict"] = "OK"
        r["note"] = f"señal OK ({n} B del 1er seg, {len(segs)} segs)"
    except requests.exceptions.ConnectTimeout:
        r["note"] = "TCP timeout (servidor no responde)"
    except requests.exceptions.ReadTimeout:
        r["verdict"] = "PARTIAL"
        r["note"] = "conecta pero no responde a tiempo"
    except requests.exceptions.SSLError as e:
        r["verdict"] = "PARTIAL"
        r["note"] = f"SSL error: {str(e)[:80]}"
    except requests.exceptions.ConnectionError as e:
        msg = str(e).lower()
        if "refused" in msg:
            r["note"] = "conn refused"
        elif "resolve" in msg or "name" in msg or "nodename" in msg:
            r["note"] = "DNS fail / dominio muerto"
        else:
            r["note"] = "conn error"
    except Exception as e:
        r["note"] = f"{type(e).__name__}: {str(e)[:90]}"
    r["elapsed"] = round(time.time() - t0, 1)
    return r


# ---------- reportes ----------

def build_md(rows, checked_at):
    ic = {"OK": "🟢 OK — recibe señal", "PARTIAL": "🟡 PARCIAL", "DEAD": "🔴 MUERTO"}
    lines = [
        "# Estado de canales — AtlasTVPilar.m3u",
        "",
        f"_Chequeo: {checked_at} — runner `ubuntu-latest` (GitHub Actions) · HEAD+primer-segmento probe_",
        "",
        "| # | Canal | Group | Veredicto | HTTP | Detalle |",
        "|---|-------|-------|-----------|------|---------|",
    ]
    for r in rows:
        url = r["url"] or "—"
        if len(url) > 130:
            url = url[:70] + " … " + url[-45:]
        extra = ""
        if r["verdict"] == "OK":
            extra = " · LIVE" if r["live"] else " · VOD"
            if r.get("targetdur"):
                extra = extra + " · seg " + str(r["targetdur"]) + "s"
        note = r["note"] + extra
        code = r["code"] if r["code"] is not None else "—"
        lines.append("| {} | {} | {} | {} | {} | {} |\n| | | | | | `{}` |".format(
            r["idx"], r["name"], r["group"], ic[r["verdict"]], code, note, url))
    ok = sum(1 for r in rows if r["verdict"] == "OK")
    par = sum(1 for r in rows if r["verdict"] == "PARTIAL")
    dead = sum(1 for r in rows if r["verdict"] == "DEAD")
    lines += ["", f"**Resumen: {ok} OK · {par} PARCIAL · {dead} MUERTO · total {len(rows)}**"]
    return "\n".join(lines)


def main():
    chans = parse_m3u(PLAYLIST_FILE)
    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(probe, c): c for c in chans}
        for f in as_completed(futs):
            rows.append(f.result())
    rows.sort(key=lambda r: r["idx"])
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open("channel_status.json", "w", encoding="utf-8") as fh:
        json.dump({"checked_at": checked_at,
                   "duration_s": round(time.time() - t0, 1),
                   "channels": rows}, fh, ensure_ascii=False, indent=1)
    md = build_md(rows, checked_at)
    with open("channel_status.md", "w", encoding="utf-8") as fh:
        fh.write(md + "\n")

    sym = {"OK": "\u25cf OK", "PARTIAL": "\u25d0 PARCIAL", "DEAD": "\u25a0 MUERTO"}
    print("=" * 110)
    print("CHECK " + checked_at + "   (" + str(round(time.time() - t0, 1)) + "s, " + str(len(rows)) + " canales)")
    print("=" * 110)
    for r in rows:
        line = (sym[r["verdict"]] + " #" + str(r["idx"]).rjust(2) + " "
                + r["name"][:42].ljust(42) + " [" + r["group"][:12] + "] "
                + "HTTP=" + str(r["code"]).ljust(4) + " " + r["note"])
        print(line)
    ok = sum(1 for r in rows if r["verdict"] == "OK")
    par = sum(1 for r in rows if r["verdict"] == "PARTIAL")
    print("")
    print("OK=" + str(ok) + "  PARTIAL=" + str(par) + "  DEAD=" + str(len(rows) - ok - par))
    for r in rows:
        print("RES {}|{}|{}|{}|{}".format(r["idx"], r["name"], r["verdict"],
                                          r["code"], r["note"]))


if __name__ == "__main__":
    main()
