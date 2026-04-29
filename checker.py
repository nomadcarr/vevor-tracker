import re
import sqlite3
import datetime
import time
import json
import os
from urllib.parse import quote

# ── Config ────────────────────────────────────────────────────────────────────

def _load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

_cfg              = _load_config()
VEVOR_DOMAIN      = _cfg.get('vevor_domain', 'www.vevor.bg')
DEBUG_SCREENSHOTS = _cfg.get('debug_screenshots', False)
REQUEST_DELAY     = _cfg.get('delay_between_checks', 3)

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')


def _search_url(q: str) -> str:
    return f"https://{VEVOR_DOMAIN}/c/search?q={quote(q)}"


# ── Screenshot helper ─────────────────────────────────────────────────────────

def _screenshot(page, name: str):
    if DEBUG_SCREENSHOTS:
        os.makedirs('debug', exist_ok=True)
        path = f'debug/{re.sub(r"[^a-zA-Z0-9_-]", "_", name)}.png'
        page.screenshot(path=path, full_page=False)
        print(f'    [debug] {path}')


# ── Stock detection ───────────────────────────────────────────────────────────

_OUT_PHRASES = [
    'out of stock', 'sold out', 'currently unavailable',
    'няма наличност', 'изчерпан', 'out-of-stock', 'notify me when available',
]
_IN_PHRASES = [
    'add to cart', 'add to bag', 'buy now',
    'добави в количката', 'добавяне в количката', 'купи сега',
    'в наличност', 'in stock',
]


def _detect_stock(page, body: str):
    is_out = any(p in body for p in _OUT_PHRASES)
    is_in  = any(p in body for p in _IN_PHRASES)
    add_btn = page.query_selector(
        'button:not([disabled])[class*="cart"],'
        'button:not([disabled])[class*="Cart"],'
        'button:not([disabled])[id*="cart"],'
        'button:not([disabled])[class*="buy"]'
    )
    if add_btn:
        is_in = True
    return is_in, is_out


def _get_product_name(page) -> str:
    for sel in ['h1', '[class*="product-title"]', '[class*="goods-name"]',
                '[class*="product-name"]', '[class*="item-title"]']:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text[:220]
    return ''


# ── Similarity scoring ────────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> float:
    """Word/number overlap similarity, 0–1. Numbers weighted 2×."""
    stop = {'the', 'and', 'for', 'with', 'set', 'kit', 'pcs', 'pce',
            'pack', 'piece', 'professional', 'industrial', 'grade', 'heavy', 'duty'}

    nums_a = set(re.findall(r'\d+(?:\.\d+)?(?:mm|cm|m|l|w|v|hz|kg|lb|in|rpm)?', a.lower()))
    nums_b = set(re.findall(r'\d+(?:\.\d+)?(?:mm|cm|m|l|w|v|hz|kg|lb|in|rpm)?', b.lower()))
    words_a = {w.lower() for w in re.findall(r'[a-zA-Z]{3,}', a) if w.lower() not in stop}
    words_b = {w.lower() for w in re.findall(r'[a-zA-Z]{3,}', b) if w.lower() not in stop}

    score = len(nums_a & nums_b) * 2 + len(words_a & words_b)
    denom = max(len(nums_a) * 2 + len(words_a), len(nums_b) * 2 + len(words_b), 1)
    return score / denom


def _search_keywords(product_name: str) -> str:
    stop = {'the', 'and', 'for', 'with', 'set', 'kit', 'pcs', 'pce',
            'professional', 'industrial', 'grade', 'heavy', 'duty', 'new'}
    words = [w for w in product_name.split()
             if re.match(r'\d', w) or (len(w) > 3 and w.lower() not in stop)]
    return ' '.join(words[:6])


# ── Result helpers ────────────────────────────────────────────────────────────

def _result(status, message, barcode='', product_name='', product_url=''):
    return {'status': status, 'message': message,
            'barcode': barcode, 'product_name': product_name, 'product_url': product_url}


# ── Core barcode checker (reuses browser context) ─────────────────────────────

def _check_barcode(context, barcode: str) -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout
    page = context.new_page()
    try:
        url = _search_url(barcode)
        print(f'    → {url}')
        try:
            page.goto(url, timeout=30_000, wait_until='domcontentloaded')
            page.wait_for_timeout(3_000)
        except PWTimeout:
            return _result('error', 'Timeout при търсене', barcode)

        _screenshot(page, f'{barcode}_search')
        body = page.inner_text('body').lower()

        no_result_hints = ['0 results', 'no results', 'no products found',
                           '0 продукта', 'не са намерени', 'няма резултати']
        if any(h in body for h in no_result_hints):
            return _result('not_found', 'Не е намерен в Vevor', barcode)

        product_el = (
            page.query_selector('a[href*="/p/"]') or
            page.query_selector('a[href*="/goods/"]') or
            page.query_selector('[class*="goods-item"] a') or
            page.query_selector('[class*="product-card"] a') or
            page.query_selector('[class*="item-card"] a')
        )
        if not product_el:
            return _result('not_found', 'Не са намерени резултати', barcode)

        href = product_el.get_attribute('href') or ''
        if href.startswith('/'):
            href = f'https://{VEVOR_DOMAIN}{href}'

        try:
            page.goto(href, timeout=30_000, wait_until='domcontentloaded')
            page.wait_for_timeout(3_000)
        except PWTimeout:
            return _result('error', 'Timeout на продуктовата страница', barcode, product_url=href)

        _screenshot(page, f'{barcode}_product')
        name = _get_product_name(page)
        body = page.inner_text('body').lower()
        is_in, is_out = _detect_stock(page, body)

        if is_out and not is_in:
            return _result('out_of_stock', 'Няма наличност', barcode, name, href)
        elif is_in:
            return _result('in_stock', 'Има наличност', barcode, name, href)
        else:
            return _result('unknown', 'Статусът е неясен', barcode, name, href)

    except Exception as e:
        print(f'    ✗ {e}')
        return _result('error', str(e)[:100], barcode)
    finally:
        page.close()


# ── Alternative stock check (by URL) ─────────────────────────────────────────

def _check_by_url(context, url: str) -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout
    page = context.new_page()
    try:
        page.goto(url, timeout=30_000, wait_until='domcontentloaded')
        page.wait_for_timeout(3_000)
        body = page.inner_text('body').lower()
        is_in, is_out = _detect_stock(page, body)
        if is_out and not is_in:
            return {'status': 'out_of_stock'}
        elif is_in:
            return {'status': 'in_stock'}
        else:
            return {'status': 'unknown'}
    except PWTimeout:
        return {'status': 'error'}
    except Exception as e:
        print(f'    ✗ alt check: {e}')
        return {'status': 'error'}
    finally:
        page.close()


# ── Alternative product research ──────────────────────────────────────────────

def _research_alternative(context, original_name: str, original_url: str):
    """
    Search Vevor for an in-stock alternative to the given product.
    Returns dict with product_name, url, similarity — or None.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    page = context.new_page()
    try:
        # Build search query from original product name
        query = _search_keywords(original_name)
        if not query:
            return None

        print(f'    [alt] Търсене: "{query}"')
        search_url = _search_url(query)

        try:
            page.goto(search_url, timeout=30_000, wait_until='domcontentloaded')
            page.wait_for_timeout(3_500)
        except PWTimeout:
            return None

        _screenshot(page, 'alt_search')

        # Collect candidate product links (skip the original)
        all_links = (
            page.query_selector_all('a[href*="/p/"]') or
            page.query_selector_all('a[href*="/goods/"]')
        )

        seen = set()
        candidates = []
        for el in all_links:
            href = el.get_attribute('href') or ''
            if href.startswith('/'):
                href = f'https://{VEVOR_DOMAIN}{href}'
            if not href or href in seen:
                continue
            # Skip the original product
            if original_url and (href == original_url or original_url.split('?')[0] in href):
                continue
            seen.add(href)
            candidates.append(href)
            if len(candidates) >= 8:
                break

        if not candidates:
            print('    [alt] Няма кандидати')
            return None

        best = None
        best_score = 0.0

        for url in candidates[:6]:
            prod_page = context.new_page()
            try:
                prod_page.goto(url, timeout=25_000, wait_until='domcontentloaded')
                prod_page.wait_for_timeout(2_500)
                _screenshot(prod_page, f'alt_candidate_{candidates.index(url)}')

                name = _get_product_name(prod_page)
                body = prod_page.inner_text('body').lower()
                is_in, is_out = _detect_stock(prod_page, body)

                if not is_in or is_out:
                    print(f'    [alt] {name[:40]}... → изчерпан, пропускам')
                    continue

                score = _similarity(original_name, name)
                print(f'    [alt] {name[:50]}... → score={score:.2f}')

                if score > best_score:
                    best_score = score
                    best = {'product_name': name, 'url': url}

            except Exception:
                pass
            finally:
                prod_page.close()

            time.sleep(1)

        if best:
            best['similarity'] = 'Идентичен' if best_score >= 0.65 else 'Сходен'
            print(f'    [alt] Намерена алтернатива: {best["product_name"][:60]} ({best["similarity"]})')
            return best

        return None

    except Exception as e:
        print(f'    [alt] Грешка: {e}')
        return None
    finally:
        page.close()


# ── DB update helpers ─────────────────────────────────────────────────────────

def update_item_status(db_path: str, barcode: str, result: dict):
    conn = sqlite3.connect(db_path)
    row  = conn.execute('SELECT id, status FROM items WHERE barcode=?', (barcode,)).fetchone()
    if not row:
        conn.close()
        return
    item_id, old_status = row
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    newly_in = result['status'] == 'in_stock' and old_status != 'in_stock'

    conn.execute('''UPDATE items SET
        status=?, last_checked=?,
        new_alert      = CASE WHEN ? THEN 1 ELSE new_alert END,
        product_name   = CASE WHEN ?!='' THEN ? ELSE product_name END,
        product_url    = CASE WHEN ?!='' THEN ? ELSE product_url END
        WHERE id=?''',
        (result['status'], now,
         newly_in,
         result['product_name'], result['product_name'],
         result['product_url'],  result['product_url'],
         item_id))
    conn.commit()
    conn.close()

    icon = {'in_stock':'✓','out_of_stock':'✗','error':'!','not_found':'?','unknown':'~'}.get(result['status'],'?')
    print(f'    {icon} {result["status"]}: {result["message"]}')
    if newly_in:
        print(f'    *** НАЛИЧНОСТ: {barcode} ***')


def _update_alt_status(db_path: str, item_id: int, status: str):
    conn = sqlite3.connect(db_path)
    row  = conn.execute('SELECT alt_status FROM items WHERE id=?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return
    old  = row[0]
    now  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    newly_in = status == 'in_stock' and old != 'in_stock'
    conn.execute('''UPDATE items SET
        alt_status=?, alt_last_checked=?,
        alt_new_alert = CASE WHEN ? THEN 1 ELSE alt_new_alert END
        WHERE id=?''', (status, now, newly_in, item_id))
    conn.commit()
    conn.close()
    if newly_in:
        print(f'    *** АЛТ. НАЛИЧНОСТ: item #{item_id} ***')


# ── Public: find alternative ──────────────────────────────────────────────────

def find_alternative_for_item(db_path: str, item_id: int):
    conn = sqlite3.connect(db_path)
    row  = conn.execute(
        'SELECT barcode, product_name, product_url FROM items WHERE id=?', (item_id,)
    ).fetchone()
    conn.close()
    if not row:
        return

    barcode, product_name, product_url = row
    print(f'\n[alt] Търся алтернатива за {barcode}…')

    def _set_search_status(s):
        c = sqlite3.connect(db_path)
        c.execute("UPDATE items SET alt_search_status=? WHERE id=?", (s, item_id))
        c.commit()
        c.close()

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
            ctx     = browser.new_context(user_agent=_UA, viewport={'width':1280,'height':800})

            # If product URL not known yet, check the barcode first
            if not product_url:
                result = _check_barcode(ctx, barcode)
                update_item_status(db_path, barcode, result)
                product_url  = result.get('product_url', '')
                product_name = result.get('product_name', '') or product_name

            if not product_url:
                browser.close()
                _set_search_status('not_found')
                return

            alt = _research_alternative(ctx, product_name, product_url)
            browser.close()

        if alt:
            c = sqlite3.connect(db_path)
            c.execute('''UPDATE items SET
                alt_product_name=?, alt_product_url=?, alt_similarity=?,
                alt_status='unknown', alt_search_status='found'
                WHERE id=?''',
                (alt['product_name'], alt['url'], alt['similarity'], item_id))
            c.commit()
            c.close()
        else:
            _set_search_status('not_found')

    except Exception as e:
        print(f'[alt] Грешка: {e}')
        _set_search_status('not_found')


# ── Public: check all items ───────────────────────────────────────────────────

def check_all_items(db_path: str):
    conn  = sqlite3.connect(db_path)
    rows  = conn.execute(
        'SELECT id, barcode, alt_product_url FROM items'
    ).fetchall()
    conn.close()

    if not rows:
        print('Няма артикули за проверка.')
        return

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'\n[{ts}] Проверка на {len(rows)} артикула…')

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('ГРЕШКА: playwright не е инсталиран.')
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx     = browser.new_context(user_agent=_UA, viewport={'width':1280,'height':800})

        for item_id, barcode, alt_url in rows:
            print(f'  Проверка: {barcode}')
            result = _check_barcode(ctx, barcode)
            update_item_status(db_path, barcode, result)

            if alt_url:
                print(f'  Проверка алтернатива за #{item_id}…')
                alt_result = _check_by_url(ctx, alt_url)
                _update_alt_status(db_path, item_id, alt_result['status'])
                icon = '✓' if alt_result['status']=='in_stock' else '✗'
                print(f'    {icon} алт: {alt_result["status"]}')

            time.sleep(REQUEST_DELAY)

        browser.close()

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] Проверката завърши.\n')
