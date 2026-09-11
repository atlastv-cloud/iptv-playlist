"""Utilidades compartidas por los updaters de la playlist.

- update_entry(): valida una URL nueva con probe real (playlist -> variante ->
  primer segmento) ANTES de escribir en la playlist. Nunca publica URLs sin verificar.
- last_good.json: registro de la última URL validada por canal (se comitea junto
  con la playlist para auditoría y recuperación).
- .reports/*.json: reporte machine-readable de cada updater (lo consume el
  workflow para el summary; no se comitea).
"""
import json
import os
import time
import warnings
from urllib.parse import urljoin

warnings.filterwarnings("ignore")
import requests

PLAYLIST_FILE = "AtlasTVPilar.m3u"
LAST_GOOD_FILE = "last_good.json"
REPORT_DIR = ".reports"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 14


def hdr(referrer=None):
    h = {"User-Agent": UA}
    if referrer:
        h["Referer"] = referrer
    return h


def probe_url(url, referrer=None, min_seg_bytes=2048):
    """(ok, nota, segundos) — HLS alcanzable y con media real en el 1er segmento."""
    t0 = time.time()
    try:
        r = requests.get(url, headers=hdr(referrer), timeout=TIMEOUT,
                         verify=False, allow_redirects=True)
        if r.status_code != 200:
            return False, "playlist HTTP " + str(r.status_code), None
        text = r.text
        if not text.lstrip().startswith("#EXTM3U"):
            return False, "respuesta no es HLS", None
        if "#EXT-X-STREAM-INF" in text:  # master -> primera variante
            variant = None
            lines = text.splitlines()
            for i, ln in enumerate(lines):
                if ln.startswith("#EXT-X-STREAM-INF"):
                    for l2 in lines[i + 1:]:
                        s2 = l2.strip()
                        if s2 and not s2.startswith("#"):
                            variant = s2
                            break
                    break
            if not variant:
                return False, "master sin variantes", None
            r = requests.get(urljoin(r.url, variant), headers=hdr(referrer),
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return False, "variante HTTP " + str(r.status_code), None
            text = r.text
        segs = [l.strip() for l in text.splitlines()
                if l.strip() and not l.strip().startswith("#")]
        if not segs:
            return False, "playlist sin segmentos", None
        base, seg = r.url, segs[0]
        if seg.lower().endswith((".m3u8", ".m3u")):  # playlist anidada
            r = requests.get(urljoin(base, seg), headers=hdr(referrer),
                             timeout=TIMEOUT, verify=False)
            if r.status_code != 200:
                return False, "sub-playlist HTTP " + str(r.status_code), None
            segs = [l.strip() for l in r.text.splitlines()
                    if l.strip() and not l.strip().startswith("#")]
            if not segs:
                return False, "sub-playlist sin segmentos", None
            base, seg = r.url, segs[0]
        with requests.get(urljoin(base, seg), headers=hdr(referrer),
                          timeout=TIMEOUT, verify=False, stream=True) as sr:
            if sr.status_code != 200:
                return False, "segmento HTTP " + str(sr.status_code), None
            n = 0
            for chunk in sr.iter_content(16384):
                n += len(chunk)
                if n >= 65536:
                    break
        if n < min_seg_bytes:
            return False, "segmento chico (" + str(n) + " B)", None
        return True, "OK (" + str(n) + " B en 1er seg)", round(time.time() - t0, 1)
    except Exception as e:
        return False, type(e).__name__ + ": " + str(e)[:110], None


def dailymotion_auto_url(video_id):
    """URL HLS firmada para un id de Dailymotion, con cadena de fallback:
       1) player/metadata API   2) config del embed (hls_source)   3) api público (hls_url).
    Devuelve (url, origen) o (None, motivos_de_fallo)."""
    import re as _re

    errors = []
    # 1) metadata API (el clásico) — para lives la respuesta cambió de forma,
    #    pruebo varias rutas conocidas del JSON
    try:
        r = requests.get("https://www.dailymotion.com/player/metadata/video/" + video_id,
                         headers=hdr(), timeout=TIMEOUT)
        if r.status_code == 200:
            try:
                data = r.json()
                q = data.get("qualities") or {}
                for key in ("auto", "hls", "hls.128"):
                    arr = q.get(key)
                    if arr and arr[0].get("url"):
                        return arr[0]["url"], "metadata:" + key
                live = data.get("live") or {}
                if isinstance(live, dict):
                    for key in ("hls", "playlist_url"):
                        if live.get(key):
                            v = live[key]
                            return (v[0]["url"] if isinstance(v, list) else v), "metadata:live"
                errors.append("metadata:sin qualities/live keys=" + ",".join(list(data)[:8]))
            except ValueError:
                errors.append("metadata:respuesta no-json")
        else:
            errors.append("metadata:HTTP" + str(r.status_code))
    except Exception as e:
        errors.append("metadata:" + type(e).__name__)
    # 2) config JSON del embed (para lives trae hls_source)
    try:
        r = requests.get("https://www.dailymotion.com/embed/video/" + video_id,
                         headers=hdr("https://www.dailymotion.com/"), timeout=TIMEOUT)
        if r.status_code == 200:
            m = _re.search(r'"hls_source"\s*:\s*"([^"]+)"', r.text)
            if m:
                return m.group(1).encode().decode("unicode_escape"), "embed"
            errors.append("embed:sin hls_source")
        else:
            errors.append("embed:HTTP" + str(r.status_code))
    except Exception as e:
        errors.append("embed:" + type(e).__name__)
    # 3) API público con la key del player (la usan los embeds para live config)
    try:
        r = requests.get("https://api.dailymotion.com/video/" + video_id,
                         params={"fields": "id,hls_url,live,qualified_videos_url", "key": "ca97"},
                         headers=hdr(), timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json() or {}
            url = d.get("hls_url")
            if url:
                return url, "api:ca97"
            live = d.get("live")
            if isinstance(live, dict) and live.get("hls_urls"):
                return list(live["hls_urls"].values())[0], "api:ca97:live"
            errors.append("api:sin hls_url keys=" + ",".join(list(d)[:6]))
        else:
            errors.append("api:HTTP" + str(r.status_code))
    except Exception as e:
        errors.append("api:" + type(e).__name__)
    # 4) endpoint de lives para reproductores (l1/live/get)
    try:
        r = requests.get("https://www.dailymotion.com/l1/live/get/" + video_id,
                         params={"stream_format": "playlist", "type": "html5",
                                 "stream_protocol": "hls"},
                         headers=hdr(), timeout=TIMEOUT)
        if r.status_code == 200:
            m = _re.search(r"https?://[^\"'\s,]+\.m3u8[^\"'\s,]*", r.text)
            if m:
                return m.group(1).encode().decode("unicode_escape"), "l1/live"
            errors.append("l1:sin m3u8 (" + r.text[:80].replace("\n", " ") + ")")
        else:
            errors.append("l1:HTTP" + str(r.status_code))
    except Exception as e:
        errors.append("l1:" + type(e).__name__)
    return None, " | ".join(errors)[:700]


def load_last_good():
    try:
        with open(LAST_GOOD_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def find_extinf(lines, title):
    """Índice de la línea #EXTINF cuyo título (post-última coma) es `title`."""
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#EXTINF:") and (s.endswith("," + title) or s.endswith("," + title + " [")):
            return i
    return -1


def report(rep):
    os.makedirs(REPORT_DIR, exist_ok=True)
    name = rep["title"].replace(" ", "_").replace("/", "-") + ".json"
    with open(os.path.join(REPORT_DIR, name), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)


def update_entry(title, url, referrer=None):
    """Valida `url` con probe; sólo si pasa, la escribe en la playlist."""
    ok, note, elapsed = probe_url(url, referrer)
    rep = {"title": title, "url": url, "valid": ok, "note": note,
           "probe_s": elapsed, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if not ok:
        rep["applied"] = False
        rep["why"] = "nuevo URL no pasó la validación; playlist intacta"
        report(rep)
        return False, "NO aplicado — validación falló: " + note
    with open(PLAYLIST_FILE, encoding="utf-8") as f:
        lines = f.readlines()
    i = find_extinf(lines, title)
    if i < 0:
        rep["applied"] = False
        rep["why"] = "canal no encontrado en la playlist"
        report(rep)
        return False, rep["why"]
    j = i + 1
    while j < len(lines) and lines[j].strip().startswith("#"):
        j += 1
    lines[j] = url + "\n"
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    lg = load_last_good()
    lg[title] = url
    with open(LAST_GOOD_FILE, "w", encoding="utf-8") as f:
        json.dump(lg, f, indent=1, ensure_ascii=False, sort_keys=True)
    rep["applied"] = True
    report(rep)
    return True, "playlist actualizada — " + note
