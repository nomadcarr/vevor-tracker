import os
import sqlite3
import threading
import atexit
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

DB_PATH = os.environ.get('DB_PATH', 'tracker.db')
PORT    = int(os.environ.get('PORT', 5000))

app = Flask(__name__)

_check_lock    = threading.Lock()
_check_running = False


# ── Database ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS items (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode          TEXT NOT NULL UNIQUE,
        name             TEXT DEFAULT '',
        order_number     TEXT DEFAULT '',
        status           TEXT DEFAULT 'pending',
        last_checked     TEXT DEFAULT NULL,
        added_at         TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
        new_alert        INTEGER DEFAULT 0,
        product_name     TEXT DEFAULT '',
        product_url      TEXT DEFAULT '',
        alt_product_name TEXT DEFAULT '',
        alt_product_url  TEXT DEFAULT '',
        alt_similarity   TEXT DEFAULT '',
        alt_status       TEXT DEFAULT '',
        alt_last_checked TEXT DEFAULT '',
        alt_new_alert    INTEGER DEFAULT 0,
        alt_search_status TEXT DEFAULT ''
    )''')

    # Migration: add columns to existing databases
    existing = {row[1] for row in conn.execute('PRAGMA table_info(items)').fetchall()}
    migrations = {
        'order_number':      'TEXT DEFAULT ""',
        'alt_product_name':  'TEXT DEFAULT ""',
        'alt_product_url':   'TEXT DEFAULT ""',
        'alt_similarity':    'TEXT DEFAULT ""',
        'alt_status':        'TEXT DEFAULT ""',
        'alt_last_checked':  'TEXT DEFAULT ""',
        'alt_new_alert':     'INTEGER DEFAULT 0',
        'alt_search_status': 'TEXT DEFAULT ""',
    }
    for col, typedef in migrations.items():
        if col not in existing:
            conn.execute(f'ALTER TABLE items ADD COLUMN {col} {typedef}')

    conn.commit()
    conn.close()


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/items', methods=['GET'])
def get_items():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM items ORDER BY new_alert DESC, alt_new_alert DESC, added_at DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/items', methods=['POST'])
def add_item():
    data         = request.get_json()
    barcode      = (data.get('barcode')      or '').strip()
    name         = (data.get('name')         or '').strip()
    order_number = (data.get('order_number') or '').strip()
    if not barcode:
        return jsonify({'error': 'Баркодът е задължителен'}), 400
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO items (barcode, name, order_number) VALUES (?, ?, ?)',
            (barcode, name, order_number)
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Баркодът вече се следи'}), 409


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    conn = get_db()
    conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/items/<int:item_id>/dismiss', methods=['POST'])
def dismiss_alert(item_id):
    conn = get_db()
    conn.execute('UPDATE items SET new_alert = 0, alt_new_alert = 0 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({'checking': _check_running})


@app.route('/api/check', methods=['POST'])
def manual_check():
    global _check_running
    if _check_running:
        return jsonify({'ok': False, 'message': 'Проверката вече е в ход'})
    threading.Thread(target=_run_check, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/items/<int:item_id>/find-alternative', methods=['POST'])
def find_alternative(item_id):
    from checker import find_alternative_for_item
    # Mark as searching immediately so UI can show spinner
    conn = get_db()
    conn.execute("UPDATE items SET alt_search_status = 'searching' WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    threading.Thread(
        target=find_alternative_for_item, args=(DB_PATH, item_id), daemon=True
    ).start()
    return jsonify({'ok': True})


@app.route('/api/items/<int:item_id>/clear-alternative', methods=['POST'])
def clear_alternative(item_id):
    conn = get_db()
    conn.execute('''UPDATE items SET
        alt_product_name='', alt_product_url='', alt_similarity='',
        alt_status='', alt_last_checked='', alt_new_alert=0, alt_search_status=''
        WHERE id=?''', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Background helpers ────────────────────────────────────────────────────────

def _run_check():
    global _check_running
    if not _check_lock.acquire(blocking=False):
        return
    _check_running = True
    try:
        from checker import check_all_items
        check_all_items(DB_PATH)
    finally:
        _check_running = False
        _check_lock.release()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    init_db()

    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(_run_check, 'interval', hours=3, id='stock_check', replace_existing=True)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

    print(f"\n{'='*50}\n  Vevor Stock Tracker → http://localhost:{PORT}\n{'='*50}\n")
    app.run(debug=False, host='0.0.0.0', port=PORT, use_reloader=False)
