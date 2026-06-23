from playwright.sync_api import sync_playwright

PLAYLIST_FILE = "AtlasTVPilar.m3u"

def get_trece_stream():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        m3u8_url = None

        def handle_request(request):
            nonlocal m3u8_url
            if (
                "live-720.m3u8" in request.url
                and "dmcdn.net" in request.url
            ):
                m3u8_url = request.url

        page.on("request", handle_request)

        page.goto("https://trece.com.py/en-vivo/", timeout=60000)

        # Esperar 10 segundos para que cargue el player
        page.wait_for_timeout(10000)

        browser.close()
        return m3u8_url


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
        print("No se encontró stream HD de Trece.")
