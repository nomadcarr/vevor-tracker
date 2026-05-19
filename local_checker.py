"""
Стартирай този скрипт на твоя компютър.
Той проверява Vevor и праща резултатите в Railway.
"""
import time
import requests as req
from checker import _check_barcode, _check_by_url, _update_alt_status

RAILWAY_URL = "https://vevor-tracker-production.up.railway.app"
DELAY       = 3   # секунди между проверките


def run():
    print(f"Свързване с {RAILWAY_URL}...")
    try:
        items = req.get(f"{RAILWAY_URL}/api/items", timeout=10).json()
    except Exception as e:
        print(f"Грешка при свързване: {e}")
        return

    print(f"Намерени {len(items)} артикула за проверка.\n")

    for item in items:
        barcode  = item['barcode']
        item_id  = item['id']
        alt_url  = item.get('alt_product_url', '')
        name     = item.get('name', '')
        print(f"  Проверка: {barcode}  ({name})")

        try:
            result = _check_barcode(barcode)
        except Exception as e:
            print(f"    ✗ Грешка: {e}")
            continue

        try:
            resp = req.post(
                f"{RAILWAY_URL}/api/items/{item_id}/update-status",
                json=result, timeout=10
            )
            icon = {'in_stock': '✓', 'almost_out': '⚠', 'out_of_stock': '✗',
                    'not_found': '?', 'error': '!', 'unknown': '~'}.get(result['status'], '~')
            print(f"    {icon} {result['status']}: {result['message']}")
            if resp.ok:
                data = resp.json()
                if data.get('newly_in'):
                    print(f"    *** НАЛИЧНОСТ! {barcode} ***")
            else:
                print(f"    ✗ Railway върна {resp.status_code} — качи app.py в GitHub!")
        except Exception as e:
            print(f"    ✗ Грешка при изпращане: {e}")

        if alt_url:
            try:
                alt_result = _check_by_url(alt_url)
                req.post(
                    f"{RAILWAY_URL}/api/items/{item_id}/update-alt-status",
                    json={'status': alt_result['status']}, timeout=10
                )
            except Exception:
                pass

        time.sleep(DELAY)

    print("\nПроверката завърши.")


if __name__ == '__main__':
    import datetime
    print(f"=== Vevor Local Checker  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    run()
