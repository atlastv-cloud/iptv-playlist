from playwright.sync_api import sync_playwright

PLAYLIST_FILE = "AtlasTVPilar.m3u"

def get_unicanal_stream():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        m3u8_url = None

        def handle_request(request):
            nonlocal m3u8_url
            if "live-720.m3u8" in request.url and "dmcdn.net" in request.url:
                m3u8_url = request.url

        page.on("request", handle_request)

        page.goto("https://unicanal.com.py/en-vivo/", timeout=60000)

        # Esperar específicamente el iframe de Dailymotion
        page.wait_for_selector('iframe[src*="dailymotion"]')

        frame = page.frame_locator('iframe[src*="dailymotion"]')

        # Click en el botón real de Play dentro del iframe
        frame.locator('button[aria-label="Play"]').click()

        # Esperar que se generen las requests del stream
        page.wait_for_timeout(12000)

        browser.close()
        return m3u8_url


def update_playlist(new_url):
    with 
