"""
TradingView webhook receiver.

Run:
    pip install flask
    python webhook_receiver.py
    # in another terminal:
    ngrok http 5000
    # use the https URL in TradingView alert -> Webhook URL, path = /tv

Alerts are appended to alerts.log as JSON lines and read by stock_analysis.py
for inclusion in the 7AM/6PM daily report.

Expected TradingView alert message (JSON):
{"secret":"<SECRET>","ticker":"{{ticker}}","price":{{close}},
 "action":"{{strategy.order.action}}","note":"MA20 cross up","time":"{{time}}"}
"""
import json
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, request, abort

SECRET = os.environ.get('TV_WEBHOOK_SECRET', 'change-me-to-a-long-random-string')
LOG_PATH = Path(__file__).parent / 'alerts.log'

# TradingView's published webhook source IPs
TV_IPS = {'52.89.214.238', '34.212.75.30', '54.218.53.128', '52.32.178.7'}

app = Flask(__name__)


@app.route('/tv', methods=['POST'])
def tv_webhook():
    src_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if src_ip and src_ip not in TV_IPS and not src_ip.startswith('127.'):
        abort(403)

    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        abort(400)

    if not isinstance(data, dict) or data.get('secret') != SECRET:
        abort(401)

    data.pop('secret', None)
    data['received_at'] = datetime.now().isoformat(timespec='seconds')

    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')

    return {'status': 'ok'}, 200


@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok', 'log': str(LOG_PATH)}, 200


if __name__ == '__main__':
    print(f'Logging alerts to: {LOG_PATH}')
    print(f'Webhook endpoint: POST /tv')
    app.run(host='0.0.0.0', port=5000)
