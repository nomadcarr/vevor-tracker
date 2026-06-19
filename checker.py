import re
import sqlite3
import datetime
import time
import json

# ── Config ────────────────────────────────────────────────────────────────────

def _load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

_cfg          = _load_config()
VEVOR_DOMAIN  = _cfg.get('vevor_domain', 'eur.vevor.com')
REQUEST_DELAY = _cfg.get('delay_between_checks', 3)


def _search_url(query: str) -> str:
    return f"https://{VEVOR_DOMAIN}/s/{query}"


# ── HTTP (curl-cffi bypasses Cloudflare TLS fingerprint) ─────────────────────

def _fetch(url: str) -> str:
    from curl_cffi import requests as cf
    r = cf.get(url, impersonate='chrome124', timeout=30,
               headers={'Accept-Language': 'en-US,en;q=0.9'})
    return r.text


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, 'html.parser')


def _body_text(html: str) -> str:
    return _soup(html).get_text(separator=' ').lower()


# ── Stock detection ───────────────────────────────────────────────────────────

_OUT_PHRASES = [
    'out of stock', 'sold out', 'currently unavailable',
    'няма наличност', 'изчерпан', 'out-of-stock', 'notify me when available',
]
_ALMOST_PHRASES = [
    'almost sold out', 'low stock', 'limited stock', 'selling fast',
    'almost gone', 'limited availability', 'nearly sold out',
    'почти разпродадено', 'ограничено количество',
]
_IN_PHRASES = [
    'add to cart', 'add to bag', 'buy now',
    'добави в количката', 'купи сега', 'в наличност', 'in stock',
]


def _detect_stock(body: str) -> str:
    is_out    = any(p in body for p in _OUT_PHRASES)
    is_almost = any(p in body for p in _ALMOST_PHRASES) or bool(re.search(r'only \d+ left', body))
    is_in     = any(p in body for p in _IN_PHRASES)

    print(f'    [phrases] out={[p for p in _OUT_PHRASES if p in body]}')
    print(f'    [phrases] almost={[p for p in _ALMOST_PHRASES if p in body]}')
    print(f'    [phrases] in={[p for p in _IN_PHRASES if p in body]}')

    status = ('almost_out'   if is_almost else
              'out_of_stock' if is_out    else
              'in_stock'     if is_in     else
              'unknown')
    print(f'    [stock] → {status}')
    return status


# ── Similarity scoring ────────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> float:
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


# ── Result helper ─────────────────────────────────────────────────────────────

def _result(status, message, barcode='', product_name='', product_url=''):
    return {'status': status, 'message': message,
            'barcode': barcode, 'product_name': product_name, 'product_url': product_url}


# ── Core barcode checker ──────────────────────────────────────────────────────

_NO_RESULT_HINTS = ['no results', 'no products', '0 results',
                    'не са намерени', 'няма резултати']
_CF_HINTS        = ['challenge', 'just a moment', 'checking your browser',
                    'enable javascript', 'ddos-guard']

_STATUS_MESSAGES = {
    'in_stock':    'Има наличност',
    'almost_out':  'Почти разпродадено',
    'out_of_stock':'Няма наличност',
    'unknown':     'Статусът е неясен',
}


def _check_barcode(barcode: str) -> dict:
    url = _search_url(barcode)
    print(f'    → {url}')
    try:
        html = _fetch(url)
    except Exception as e:
        return _result('error', str(e)[:100], barcode)

    body = _body_text(html)
    print(f'    [body_preview] {repr(body[:400])}')

    if any(h in body for h in _CF_HINTS):
        print('    [blocked] Cloudflare challenge')
        return _result('error', 'Cloudflare блок', barcode)

    if any(h in body for h in _NO_RESULT_HINTS):
        return _result('not_found', 'Не е намерен в Vevor', barcode)

    # First product link
    s = _soup(html)
    link_el = s.find('a', href=re.compile(r'/p/'))
    href = ''
    if link_el:
        href = link_el['href']
        if href.startswith('/'):
            href = f'https://{VEVOR_DOMAIN}{href}'

    # Product name from first h2/h3 in search cards or h1
    name = ''
    for tag in ['h1', 'h2', 'h3']:
        el = s.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) > 5:
                name = t[:220]
                break

    status = _detect_stock(body)

    if not href and status == 'unknown':
        return _result('not_found', 'Не са намерени резултати', barcode)

    return _result(status, _STATUS_MESSAGES.get(status, ''), barcode, name, href)


def _check_by_url(url: str) -> dict:
    try:
        html  = _fetch(url)
        body  = _body_text(html)
        return {'status': _detect_stock(body)}
    except Exception as e:
        print(f'    ✗ alt check: {e}')
        return {'status': 'error'}


# ── Alternative product research ──────────────────────────────────────────────

def _research_alternative(original_name: str, original_url: str):
    query = _search_keywords(original_name)
    if not query:
        return None

    print(f'    [alt] Търсене: "{query}"')
    try:
        html = _fetch(_search_url(query))
    except Exception:
        return None

    s = _soup(html)
    seen, candidates = set(), []
    for a in s.find_all('a', href=re.compile(r'/p/')):
        href = a['href']
        if href.startswith('/'):
            href = f'https://{VEVOR_DOMAIN}{href}'
        if href in seen:
            continue
        if original_url and (href == original_url or original_url.split('?')[0] in href):
            continue
        seen.add(href)
        candidates.append(href)
        if len(candidates) >= 8:
            break

    if not candidates:
        print('    [alt] Няма кандидати')
        return None

    best, best_score = None, 0.0
    for url in candidates[:6]:
        try:
            html2  = _fetch(url)
            body2  = _body_text(html2)
            status = _detect_stock(body2)
            if status not in ('in_stock', 'almost_out'):
                continue
            s2   = _soup(html2)
            name = ''
            for tag in ['h1', 'h2']:
                el = s2.find(tag)
                if el:
                    t = el.get_text(strip=True)
                    if t and len(t) > 5:
                        name = t[:220]
                        break
            score = _similarity(original_name, name)
            print(f'    [alt] {name[:50]}… score={score:.2f}')
            if score > best_score:
                best_score = score
                best = {'product_name': name, 'url': url}
        except Exception:
            pass
        time.sleep(1)

    if best:
        best['similarity'] = 'Идентичен' if best_score >= 0.65 else 'Сходен'
        return best
    return None


# ── DB update helpers ─────────────────────────────────────────────────────────

def update_item_status(db_path: str, barcode: str, result: dict):
    conn = sqlite3.connect(db_path)
    row  = conn.execute('SELECT id, status FROM items WHERE barcode=?', (barcode,)).fetchone()
    if not row:
        conn.close()
        return
    item_id, old_status = row
    now      = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    available = ('in_stock', 'almost_out')
    newly_in  = result['status'] in available and old_status not in available
    conn.execute('''UPDATE items SET
        status=?, last_checked=?,
        new_alert    = CASE WHEN ? THEN 1 ELSE new_alert END,
        product_name = CASE WHEN ?!='' THEN ? ELSE product_name END,
        product_url  = CASE WHEN ?!='' THEN ? ELSE product_url END
        WHERE id=?''',
        (result['status'], now, newly_in,
         result['product_name'], result['product_name'],
         result['product_url'],  result['product_url'], item_id))
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
    old      = row[0]
    now      = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

    def _set(s):
        c = sqlite3.connect(db_path)
        c.execute("UPDATE items SET alt_search_status=? WHERE id=?", (s, item_id))
        c.commit()
        c.close()

    try:
        if not product_url:
            r = _check_barcode(barcode)
            update_item_status(db_path, barcode, r)
            product_url  = r.get('product_url', '')
            product_name = r.get('product_name', '') or product_name

        if not product_url:
            _set('not_found')
            return

        alt = _research_alternative(product_name, product_url)
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
            _set('not_found')
    except Exception as e:
        print(f'[alt] Грешка: {e}')
        _set('not_found')


# ── Public: check all items ───────────────────────────────────────────────────

def check_all_items(db_path: str):
    conn = sqlite3.connect(db_path)
    rows = conn.execute('SELECT id, barcode, alt_product_url FROM items').fetchall()
    conn.close()

    if not rows:
        print('Няма артикули за проверка.')
        return

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'\n[{ts}] Проверка на {len(rows)} артикула…')

    for item_id, barcode, alt_url in rows:
        print(f'  Проверка: {barcode}')
        result = _check_barcode(barcode)
        update_item_status(db_path, barcode, result)

        if alt_url:
            print(f'  Проверка алтернатива за #{item_id}…')
            alt_result = _check_by_url(alt_url)
            _update_alt_status(db_path, item_id, alt_result['status'])
            icon = '✓' if alt_result['status'] == 'in_stock' else '✗'
            print(f'    {icon} алт: {alt_result["status"]}')

        time.sleep(REQUEST_DELAY)

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] Проверката завърши.\n')
