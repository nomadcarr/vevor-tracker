import os
import sqlite3
import datetime
import traceback
from flask import Flask, render_template, request, jsonify

DB_PATH = os.environ.get('DB_PATH', 'tracker.db')
PORT    = int(os.environ.get('PORT', 5000))

app = Flask(__name__)


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
    try:
        conn = get_db()
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        print(f"DELETE ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/items/<int:item_id>/dismiss', methods=['POST'])
def dismiss_alert(item_id):
    conn = get_db()
    conn.execute('UPDATE items SET new_alert = 0, alt_new_alert = 0 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({'checking': False, 'version': '3'})


@app.route('/api/debug', methods=['GET'])
def debug_info():
    import stat
    db_dir = os.path.dirname(DB_PATH) or '.'
    db_exists = os.path.exists(DB_PATH)
    info = {
        'DB_PATH': DB_PATH,
        'db_exists': db_exists,
        'dir_writable': os.access(db_dir, os.W_OK),
        'file_writable': os.access(DB_PATH, os.W_OK) if db_exists else None,
        'dir_stat': oct(stat.S_IMODE(os.stat(db_dir).st_mode)),
        'file_stat': oct(stat.S_IMODE(os.stat(DB_PATH).st_mode)) if db_exists else None,
    }
    try:
        conn = get_db()
        conn.execute('CREATE TABLE IF NOT EXISTS _test (x INTEGER)')
        conn.execute('INSERT INTO _test VALUES (1)')
        conn.execute('DELETE FROM _test')
        conn.commit()
        conn.close()
        info['write_test'] = 'OK'
    except Exception as e:
        info['write_test'] = str(e)
    return jsonify(info)


@app.route('/api/check', methods=['POST'])
def manual_check():
    return jsonify({'ok': False, 'message': 'Проверката се извършва от локалния компютър. Пусни python local_checker.py'})


@app.route('/api/items/<int:item_id>/update-status', methods=['POST'])
def update_item_status(item_id):
    data         = request.get_json()
    status       = data.get('status', 'unknown')
    product_name = (data.get('product_name') or '').strip()
    product_url  = (data.get('product_url')  or '').strip()

    conn = get_db()
    row  = conn.execute('SELECT status FROM items WHERE id=?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    old_status = row['status']
    now        = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    available  = ('in_stock', 'almost_out')
    newly_in   = status in available and old_status not in available

    try:
        conn.execute('''UPDATE items SET
            status=?, last_checked=?,
            new_alert    = CASE WHEN ? THEN 1 ELSE new_alert END,
            product_name = CASE WHEN length(?)>0 THEN ? ELSE product_name END,
            product_url  = CASE WHEN length(?)>0 THEN ? ELSE product_url END
            WHERE id=?''',
            (status, now, 1 if newly_in else 0,
             product_name, product_name,
             product_url,  product_url, item_id))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'newly_in': newly_in})
    except Exception as e:
        print(f"UPDATE ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/items/<int:item_id>/find-alternative', methods=['POST'])
def find_alternative(item_id):
    return jsonify({'ok': False, 'message': 'Не е налично'}), 200


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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    try:
        init_db()
    except Exception as e:
        print(f"init_db warning (ще се опита пак при заявка): {e}", flush=True)
    print(f"\n{'='*50}\n  Vevor Stock Tracker → http://localhost:{PORT}\n{'='*50}\n")
    app.run(debug=False, host='0.0.0.0', port=PORT, use_reloader=False)
