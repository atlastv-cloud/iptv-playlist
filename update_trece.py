import requests

PLAYLIST_FILE = "AtlasTVPilar.m3u"
VIDEO_ID = "k4nLYiNrBX8W5jDbSlM"

def get_trece_stream():
    url = f"https://www.dailymotion.com/player/metadata/video/{VIDEO_ID}"
    response = requests.get(url, timeout=15)

    if response.status_code != 200:
        return None

    data = response.json()

    try:
        hls_url = data["qualities"]["auto"][0]["url"]
        return hls_url
    except (KeyError, IndexError):
        return None


def update_playlist(new_url):
    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i in range(len(lines)):
        if lines[i].strip() == "#EXTINF:-1,Trece":
            lines[i + 1] = new_url + "\n"
            break

    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


if __name__ == "__main__":
    url = get_trece_stream()
    if url:
        update_playlist(url)
        print("Trece actualizado:", url)
    else:
        print("No se pudo obtener stream de Trece.")
