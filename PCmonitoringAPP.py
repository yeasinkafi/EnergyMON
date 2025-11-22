from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import requests, time, hmac, hashlib, json, sqlite3, os, threading, zipfile, io, csv
from datetime import datetime, timedelta

# ---------------- App ----------------
app = Flask("EnergyMon")
# Allow frontend hosted on GitHub Pages (and local dev) to call this API
CORS(app, resources={r"/*": {"origins": "*"}})   # you can later restrict to ['https://yeasinkafi.github.io']
start_time = time.time()

# ---------------- Tuya config (env override supported) ----------------
ACCESS_ID     = os.getenv('TUYA_ACCESS_ID', '4jv3d75ewcjmneaxws9n')
ACCESS_SECRET = os.getenv('TUYA_ACCESS_SECRET', 'ec03630d3c4e4d30ab7d649ffb6a5d19')
DEVICE_ID     = os.getenv('TUYA_DEVICE_ID', 'bfe511cad106798e69ffht')
# Make sure this matches your Tuya Cloud project region
BASE_URL      = os.getenv('TUYA_BASE_URL', 'https://openapi.tuyaeu.com')

# ---------------- Database ----------------
is_on_render = 'RENDER' in os.environ
DB_PATH = '/var/data/power.db' if is_on_render else 'power.db'

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    print(f"Initializing database at: {DB_PATH}")
    conn = get_conn()
    conn.execute('''CREATE TABLE IF NOT EXISTS readings
                    (ts INTEGER PRIMARY KEY, voltage REAL, current REAL, power REAL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts)')
    conn.commit()
    conn.close()

init_db()

# ---------------- Tuya helpers ----------------
def sign(method, path, body='', token=''):
    t = str(int(time.time() * 1000))
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    msg = ACCESS_ID + (token or '') + t + f"{method}\n{payload_hash}\n\n{path}"
    return t, hmac.new(ACCESS_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()

def _tuya_get(url, headers):
    r = requests.get(url, headers=headers, timeout=10)
    j = r.json()
    if not j.get("success", False):
        print("Tuya GET error:", j)
        raise RuntimeError(f"Tuya GET failed: {j.get('code')} {j.get('msg')}")
    if "result" not in j:
        print("Tuya GET missing 'result':", j)
        raise KeyError("result")
    return j["result"]

def _tuya_post(url, headers, body):
    r = requests.post(url, headers=headers, data=body, timeout=10)
    j = r.json()
    if not j.get("success", False):
        print("Tuya POST error:", j)
        raise RuntimeError(f"Tuya POST failed: {j.get('code')} {j.get('msg')}")
    if "result" not in j:
        print("Tuya POST missing 'result':", j)
        raise KeyError("result")
    return j["result"]

def get_token():
    t, sig = sign('GET', '/v1.0/token?grant_type=1')
    headers = {'client_id': ACCESS_ID, 'sign': sig, 't': t, 'sign_method': 'HMAC-SHA256'}
    return _tuya_get(BASE_URL + '/v1.0/token?grant_type=1', headers)['access_token']

# switch code
SWITCH_CODE = 'switch_1'

def get_device_data():
    """Return (voltage V, current A, power W, switch bool) directly from Tuya."""
    global SWITCH_CODE
    token = get_token()
    path = f'/v1.0/devices/{DEVICE_ID}/status'
    t, sig = sign('GET', path, '', token)
    headers = {
        'client_id': ACCESS_ID,
        'access_token': token,
        'sign': sig,
        't': t,
        'sign_method': 'HMAC-SHA256'
    }

    result = _tuya_get(BASE_URL + path, headers)  # list of {code, value}
    codes = {d.get('code'): d.get('value') for d in result if isinstance(d, dict)}
    if SWITCH_CODE not in codes and 'switch' in codes:
        SWITCH_CODE = 'switch'

    switch_raw = bool(codes.get(SWITCH_CODE, False))
    voltage = (codes.get('cur_voltage', 0) or 0) / 10
    current = (codes.get('cur_current', 0) or 0) / 1000
    power   = (codes.get('cur_power',   0) or 0) / 10
    return voltage, current, power, switch_raw

# ---------------- Background collector ----------------
def collect_data_periodically():
    print("Starting background data collection thread...")
    while True:
        try:
            voltage, current, power, switch = get_device_data()
            if switch:
                ts = int(time.time())
                conn = get_conn()
                conn.execute(
                    'INSERT OR IGNORE INTO readings VALUES (?,?,?,?)',
                    (ts, voltage, current, power)
                )
                conn.commit()
                conn.close()
                print(f"Saved reading: {power:.1f} W")
            else:
                print("Device OFF; not saving.")
        except Exception as e:
            print("Collector error:", e)
        time.sleep(15)

# ---------------- APIs ----------------
@app.route('/api/live')
def api_live():
    try:
        voltage, current, power, switch = get_device_data()
        return jsonify({
            'switch': switch,
            'power': power,
            'voltage': voltage,
            'current': current,
            'server_time': int(time.time())  # for “Last Update”
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/summary')
def api_summary():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = int(today_start.timestamp())
    conn = get_conn()
    energy_ws = conn.execute(
        "SELECT COALESCE(SUM(power),0)*15 FROM readings WHERE ts >= ?",
        (start_ts,)
    ).fetchone()[0]
    energy_kwh = (energy_ws / 3600.0) / 1000.0
    runtime_seconds = conn.execute(
        "SELECT COUNT(*)*15 FROM readings WHERE ts >= ? AND power > 10",
        (start_ts,)
    ).fetchone()[0]
    conn.close()
    return jsonify({
        'today_energy_kwh': round(energy_kwh, 3),
        'daily_runtime_seconds': int(runtime_seconds or 0)
    })

def _window_bounds(granularity, hours=None, days=None, weeks=None):
    now = int(time.time())
    if granularity == 'minute':
        span = int((hours or 2) * 3600)
    elif granularity == 'hour':
        span = int((hours or 48) * 3600)
    elif granularity == 'day':
        span = int((days or 30) * 86400)
    elif granularity == 'week':
        span = int((weeks or 12) * 7 * 86400)
    else:
        raise ValueError("Invalid granularity")
    return now - span, now

def _bucket_seconds(granularity):
    return {
        'minute': 60,
        'hour': 3600,
        'day': 86400,
        'week': 7*86400
    }[granularity]

@app.route('/api/series')
def api_series():
    """
    /api/series?granularity=minute|hour|day|week
    Returns [{ ts(ms), avg_power, energy_kwh, count }]
    """
    gran = (request.args.get('granularity') or 'minute').lower()
    if gran not in ('minute', 'hour', 'day', 'week'):
        return jsonify({'error': 'granularity must be minute|hour|day|week'}), 400

    # Parse optional window params (still used for minute/hour)
    try:
        hours = float(request.args.get('hours')) if request.args.get('hours') else None
        days  = float(request.args.get('days'))  if request.args.get('days')  else None
        weeks = float(request.args.get('weeks')) if request.args.get('weeks') else None
    except ValueError:
        return jsonify({'error': 'hours/days/weeks must be numeric'}), 400

    conn = get_conn()

    # ---------- MINUTE / HOUR ----------
    if gran in ('minute', 'hour'):
        start_ts, end_ts = _window_bounds(gran, hours, days, weeks)
        bucket = _bucket_seconds(gran)

        rows = conn.execute(f'''
            SELECT
                (ts / ?) * ? AS bucket_ts,
                COUNT(*) AS n,
                AVG(power) AS avg_power,
                SUM(power) AS sum_power
            FROM readings
            WHERE ts >= ? AND ts <= ?
            GROUP BY bucket_ts
            ORDER BY bucket_ts
        ''', (bucket, bucket, start_ts, end_ts)).fetchall()

        conn.close()

        series = []
        for r in rows:
            n = int(r['n'])
            avg_p = float(r['avg_power'] or 0.0)
            sum_p = float(r['sum_power'] or 0.0)
            energy_kwh = (sum_p * 15.0) / 3600.0 / 1000.0
            series.append({
                'ts': int(r['bucket_ts']) * 1000,
                'avg_power': round(avg_p, 3),
                'energy_kwh': float(f"{energy_kwh:.6f}"),
                'count': n
            })
        return jsonify(series)

    # ---------- DAY: 24 hourly buckets for TODAY ----------
    if gran == 'day':
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = int(today_start.timestamp())
        end_ts = int((today_start + timedelta(days=1)).timestamp()) - 1
        bucket = 3600  # 1 hour

        rows = conn.execute('''
            SELECT
                (ts / ?) * ? AS bucket_ts,
                COUNT(*) AS n,
                AVG(power) AS avg_power,
                SUM(power) AS sum_power
            FROM readings
            WHERE ts >= ? AND ts <= ?
            GROUP BY bucket_ts
            ORDER BY bucket_ts
        ''', (bucket, bucket, start_ts, end_ts)).fetchall()

        bucket_map = {int(r['bucket_ts']): r for r in rows}

        series = []
        for i in range(24):
            bucket_ts = start_ts + i * bucket
            r = bucket_map.get(bucket_ts)
            if r:
                n = int(r['n'])
                avg_p = float(r['avg_power'] or 0.0)
                sum_p = float(r['sum_power'] or 0.0)
            else:
                n = 0
                avg_p = 0.0
                sum_p = 0.0

            energy_kwh = (sum_p * 15.0) / 3600.0 / 1000.0
            series.append({
                'ts': bucket_ts * 1000,
                'avg_power': round(avg_p, 3),
                'energy_kwh': float(f"{energy_kwh:.6f}"),
                'count': n
            })

        conn.close()
        return jsonify(series)

    # ---------- WEEK: 7 daily buckets for last 7 days ----------
    if gran == 'week':
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=6)
        start_ts = int(week_start.timestamp())
        end_ts = int((today_start + timedelta(days=1)).timestamp()) - 1
        bucket = 86400  # 1 day

        rows = conn.execute('''
            SELECT
                (ts / ?) * ? AS bucket_ts,
                COUNT(*) AS n,
                AVG(power) AS avg_power,
                SUM(power) AS sum_power
            FROM readings
            WHERE ts >= ? AND ts <= ?
            GROUP BY bucket_ts
            ORDER BY bucket_ts
        ''', (bucket, bucket, start_ts, end_ts)).fetchall()

        bucket_map = {int(r['bucket_ts']): r for r in rows}

        series = []
        for i in range(7):
            bucket_ts = start_ts + i * bucket
            r = bucket_map.get(bucket_ts)
            if r:
                n = int(r['n'])
                avg_p = float(r['avg_power'] or 0.0)
                sum_p = float(r['sum_power'] or 0.0)
            else:
                n = 0
                avg_p = 0.0
                sum_p = 0.0

            energy_kwh = (sum_p * 15.0) / 3600.0 / 1000.0
            series.append({
                'ts': bucket_ts * 1000,
                'avg_power': round(avg_p, 3),
                'energy_kwh': float(f"{energy_kwh:.6f}"),
                'count': n
            })

        conn.close()
        return jsonify(series)

@app.route('/api/history')
def api_history():
    date_str = request.args.get('date')
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    start_ts = int(query_date.timestamp())
    end_ts = int((query_date + timedelta(days=1)).timestamp())
    conn = get_conn()
    rows = conn.execute('''
        SELECT 
            (ts / 600) * 600 as interval_ts,
            AVG(power) as avg_power
        FROM readings
        WHERE ts >= ? AND ts < ?
        GROUP BY interval_ts
        ORDER BY interval_ts
    ''', (start_ts, end_ts)).fetchall()
    conn.close()
    return jsonify([
        {'x': int(r['interval_ts']) * 1000, 'y': float(r['avg_power'] or 0)}
        for r in rows
    ])

@app.route('/api/system')
def api_system():
    return jsonify({'uptime_seconds': time.time() - start_time})

@app.route('/switch', methods=['POST'])
def switch_power():
    """Toggle device power ON/OFF. Auto-detects dp code (switch_1 vs switch) and retries once."""
    global SWITCH_CODE
    on = bool(request.json.get('on', False))
    token = get_token()

    def send(code):
        body = json.dumps({"commands": [{"code": code, "value": on}]})
        t, sig = sign('POST', f'/v1.0/devices/{DEVICE_ID}/commands', body, token)
        headers = {
            'client_id': ACCESS_ID,
            'access_token': token,
            'sign': sig,
            't': t,
            'sign_method': 'HMAC-SHA256',
            'Content-Type': 'application/json'
        }
        return _tuya_post(BASE_URL + f'/v1.0/devices/{DEVICE_ID}/commands', headers, body)

    try:
        send(SWITCH_CODE)
        return jsonify({'success': True, 'code_used': SWITCH_CODE})
    except Exception:
        alt = 'switch' if SWITCH_CODE == 'switch_1' else 'switch_1'
        try:
            send(alt)
            SWITCH_CODE = alt
            return jsonify({'success': True, 'code_used': SWITCH_CODE})
        except Exception as e2:
            return jsonify({'success': False, 'error': str(e2)}), 500

# ---------------- CSV Export as ZIP (with readable 12h time) ----------------
def convert_ts_12h(unix_ts):
    """Convert UNIX timestamp to 12-hour format with AM/PM."""
    try:
        return datetime.fromtimestamp(int(unix_ts)).strftime("%Y-%m-%d %I:%M:%S %p")
    except Exception:
        return ""

def export_sqlite_to_csv_memory():
    """Exports all tables to CSV and returns ZIP bytes in memory."""
    conn = get_conn()
    cur = conn.cursor()

    # Fetch tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cur.fetchall()]

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for table in tables:
            cur.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]

            # If table has ts column, append readable_time
            if "ts" in col_names:
                ts_index = col_names.index("ts")
                col_names_with_rt = col_names + ["readable_time"]
                updated_rows = []
                for row in rows:
                    row = list(row)
                    unix_ts = row[ts_index]
                    human_time = convert_ts_12h(unix_ts)
                    row.append(f'="{human_time}"')  # Excel-safe text
                    updated_rows.append(row)

                rows_to_write = updated_rows
                header = col_names_with_rt
            else:
                rows_to_write = [list(r) for r in rows]
                header = col_names

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(header)
            writer.writerows(rows_to_write)

            zipf.writestr(f"{table}.csv", csv_buffer.getvalue())

    conn.close()
    mem_zip.seek(0)
    return mem_zip

@app.route("/download-csv")
def download_csv():
    """Download all database tables as a ZIP file."""
    zip_file = export_sqlite_to_csv_memory()
    return send_file(
        zip_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="energy_data_csv.zip"
    )

# ---------------- Frontend ----------------
@app.route('/')
def index():
    # You won't usually hit this when using GitHub Pages, but it's handy for local testing
    return render_template('dashboard.html', device_id=DEVICE_ID)

# ---------------- Main ----------------
if __name__ == '__main__':
    threading.Thread(target=collect_data_periodically, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=5000)
