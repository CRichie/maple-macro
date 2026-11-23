import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from macro import Macro, user32

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'macro-config.json'
DEFAULTS = {'attack':'a', 'random_keys':'', 'skill1':'s', 'skill2':'d',
 'interval_min':'110', 'interval_max':'120', 'action_min':'0.25', 'action_max':'0.8',
 'teleport_min':'1.2', 'teleport_max':'1.8', 'press_min':'0.06', 'press_max':'0.10',
 'skill_wait_min':'0.4', 'skill_wait_max':'0.6', 'stay_min':'5', 'stay_max':'10',
 'skills':'1,2,2,2'}
TOKEN = secrets.token_urlsafe(24)

class Field:
    def __init__(self, value): self.value = str(value)
    def get(self): return self.value

class Engine(Macro):
    def __init__(self):
        self.stop = threading.Event()
        self.worker = None
        self.lock = threading.Lock()
        self.config_data = DEFAULTS.copy()
        self.message = '已停止'
        if CONFIG.exists():
            try:
                stored = json.loads(CONFIG.read_text(encoding='utf-8'))
                if 'teleport_wait' in stored:
                    stored.setdefault('teleport_min', stored['teleport_wait'])
                    stored.setdefault('teleport_max', stored['teleport_wait'])
                candidate = {k: str(stored.get(k, v)) for k, v in DEFAULTS.items()}
                self.validate(candidate)
                self.config_data = candidate
            except (ValueError, TypeError, OSError, AttributeError):
                self.message = '配置文件无效，已使用默认值'
        threading.Thread(target=self.hotkeys, daemon=True).start()

    def validate(self, data):
        self.vars = {k: Field(data[k]) for k in DEFAULTS}
        return Macro.config(self)

    def save(self, data):
        if not isinstance(data, dict) or set(data) != set(DEFAULTS):
            raise ValueError('配置字段不完整')
        candidate = {k: str(data[k]).strip() for k in DEFAULTS}
        with self.lock:
            self.validate(candidate)
            CONFIG.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
            self.config_data = candidate
            self.message = '配置已保存；运行中的参数将在下次启动时生效'

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive(): return
            cfg = self.validate(self.config_data)
            self.stop.clear()
            self.message = '运行中：3 秒后开始，请切换至游戏；F9 停止'
            self.worker = threading.Thread(target=self.run, args=(cfg,), daemon=True)
            self.worker.start()

    def halt(self):
        self.stop.set()
        self.message = '已停止'

    def hotkeys(self):
        previous = {0x77: False, 0x78: False}
        while True:
            for code, action in ((0x77, self.start), (0x78, self.halt)):
                down = bool(user32.GetAsyncKeyState(code) & 0x8000)
                if down and not previous[code]: action()
                previous[code] = down
            time.sleep(0.05)

engine = Engine()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def reply(self, code, body, kind='application/json; charset=utf-8'):
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def authorized(self):
        return secrets.compare_digest(self.headers.get('X-Macro-Token', ''), TOKEN)
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/' and secrets.compare_digest(parse_qs(parsed.query).get('token', [''])[0], TOKEN):
            return self.reply(200, (HERE / 'macro.html').read_bytes(), 'text/html; charset=utf-8')
        if parsed.path == '/test' and secrets.compare_digest(parse_qs(parsed.query).get('token', [''])[0], TOKEN):
            return self.reply(200, (HERE / 'macro_test.html').read_bytes(), 'text/html; charset=utf-8')
        if parsed.path == '/api/state' and self.authorized():
            return self.reply(200, {'config':engine.config_data, 'message':engine.message, 'running': bool(engine.worker and engine.worker.is_alive())})
        self.reply(404, {'error':'未找到'})
    def do_POST(self):
        if not self.authorized(): return self.reply(403, {'error':'无权限'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 16384: raise ValueError('请求过大')
            data = json.loads(self.rfile.read(length) or b'{}')
            if self.path == '/api/config': engine.save(data)
            elif self.path == '/api/start': engine.start()
            elif self.path == '/api/stop': engine.halt()
            else: return self.reply(404, {'error':'未找到'})
            self.reply(200, {'message':engine.message})
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.reply(400, {'error':str(exc)})

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/?token={TOKEN}'
    print('本地页面：' + url, flush=True)
    print('F8 启动，F9 停止；关闭此窗口或按 Ctrl+C 退出。', flush=True)
    webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        engine.halt()
        server.server_close()
