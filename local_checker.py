"""
Стартирай на твоя компютър (НЕ Railway).
Използва реален Chrome браузър — минава Cloudflare.

Инсталация (само веднъж):
    python -m pip install playwright requests
    python -m playwright install chromium
"""
import re
import time
import random
import datetime
import subprocess
import requests as req
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

try:
    import winsound
    def _alert_sound():
        for _ in range(5):
            winsound.Beep(1000, 400)
            time.sleep(0.15)
except ImportError:
    def _alert_sound():
        pass


def _alert_notify(barcode, name, status):
    _alert_sound()
    label = 'НАЛИЧНО' if status == 'in_stock' else 'ПОЧТИ РАЗПРОДАДЕНО'
    msg   = f"{label}: {name or barcode}"
    try:
        subprocess.Popen([
            'powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command',
            f'''Add-Type -AssemblyName System.Windows.Forms;
[System.Windows.Forms.MessageBox]::Show("{msg}", "Vevor Stock Alert",
[System.Windows.Forms.MessageBoxButtons]::OK,
[System.Windows.Forms.MessageBoxIcon]::Information)'''
        ])
    except Exception:
        pass

RAILWAY_URL = "https://vevor-tracker-production.up.railway.app"
VEVOR       = "eur.vevor.com"
DELAY_MIN   = 5
DELAY_MAX   = 10

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

_OUT_PHRASES    = ['out of stock','sold out','currently unavailable',
                   'няма наличност','изчерпан','out-of-stock']
_ALMOST_PHRASES = ['almost sold out','almost gone','nearly sold out',
                   'почти разпродадено']
_IN_PHRASES     = ['add to cart','add to bag','buy now',
                   'добави в количката','купи сега','в наличност','in stock']

_CF_HINTS = ['just a moment','checking your browser','enable javascript',
             'ddos-guard','challenge','verify you are human']

_STATUS_MSG = {
    'in_stock':    'Има наличност',
    'almost_out':  'Почти разпродадено',
    'out_of_stock':'Няма наличност',
    'unknown':     'Статусът е неясен',
    'not_found':   'Не е намерен',
    'error':       'Грешка',
}


def _detect(body):
    is_out    = any(p in body for p in _OUT_PHRASES)
    is_almost = any(p in body for p in _ALMOST_PHRASES) or bool(re.search(r'only \d+ left', body))
    is_in     = any(p in body for p in _IN_PHRASES)
    # out_of_stock takes priority — explicit "sold out" beats "only X left"
    return ('out_of_stock' if is_out    else
            'almost_out'   if is_almost else
            'in_stock'     if is_in     else
            'unknown')


def _check(page, barcode):
    url = f"https://{VEVOR}/s/{barcode}"
    print(f"    → {url}")
    try:
        page.goto(url, timeout=35_000, wait_until='domcontentloaded')
        page.wait_for_timeout(4_000)
    except PWTimeout:
        return {'status': 'error', 'message': 'Timeout', 'product_name': '', 'product_url': ''}

    body = page.inner_text('body').lower()

    if any(h in body for h in _CF_HINTS):
        print("    [CF] Cloudflare challenge — изчаквам 30с...")
        time.sleep(30)
        body = page.inner_text('body').lower()
        if any(h in body for h in _CF_HINTS):
            return {'status': 'error', 'message': 'Cloudflare блок', 'product_name': '', 'product_url': ''}

    no_result = ['no results','no products','0 results','не са намерени','няма резултати']
    if any(h in body for h in no_result):
        return {'status': 'not_found', 'message': 'Не е намерен', 'product_name': '', 'product_url': ''}

    status = _detect(body)
    print(f"    [stock] → {status}")

    link = page.query_selector('a[href*="/p/"]')
    href = ''
    if link:
        href = link.get_attribute('href') or ''
        if href.startswith('/'):
            href = f'https://{VEVOR}{href}'

    name_el = page.query_selector('h1') or page.query_selector('h2')
    name = name_el.inner_text().strip()[:200] if name_el else ''

    if not link and status == 'unknown':
        return {'status': 'not_found', 'message': 'Не са намерени резултати', 'product_name': '', 'product_url': ''}

    return {'status': status, 'message': _STATUS_MSG.get(status, ''),
            'product_name': name, 'product_url': href}


def _send(item_id, result, item):
    try:
        resp = req.post(f"{RAILWAY_URL}/api/items/{item_id}/update-status",
                        json=result, timeout=10)
        if resp.ok:
            data = resp.json()
            if data.get('newly_in'):
                print(f"    *** НАЛИЧНОСТ! ***")
                _alert_notify(item.get('barcode', ''), item.get('name', ''), result['status'])
        else:
            print(f"    ✗ Railway {resp.status_code} — кач app.py в GitHub ако е нов endpoint")
    except Exception as e:
        print(f"    ✗ Грешка при изпращане: {e}")


def run():
    print(f"Свързване с {RAILWAY_URL}...")
    try:
        items = req.get(f"{RAILWAY_URL}/api/items", timeout=10).json()
    except Exception as e:
        print(f"Грешка: {e}")
        return

    print(f"{len(items)} артикула за проверка.\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent=_UA,
            viewport={'width': 1280, 'height': 800},
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        for i, item in enumerate(items):
            barcode = item['barcode']
            name    = item.get('name', '')
            print(f"  [{i+1}/{len(items)}] {barcode}  ({name})")

            result = _check(page, barcode)
            icon   = {'in_stock':'✓','almost_out':'⚠','out_of_stock':'✗',
                      'not_found':'?','error':'!','unknown':'~'}.get(result['status'],'~')
            print(f"    {icon} {result['status']}: {result['message']}")

            _send(item['id'], result, item)

            if i < len(items) - 1:
                d = random.uniform(DELAY_MIN, DELAY_MAX)
                print(f"    (пауза {d:.0f}с)")
                time.sleep(d)

        browser.close()

    print("\nПроверката завърши.")


if __name__ == '__main__':
    print(f"=== Vevor Checker  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    run()
