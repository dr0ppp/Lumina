"""Authenticated loopback-only bridge shared by browser and UXP clients."""

from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import secrets
import sqlite3
from threading import Timer
import webbrowser
import zipfile

from ..ai.client import ModelConfig
from ..ai.validation import load_json
from ..errors import LuminaError
from .workspace import Workspace

ASSETS = ('index.html', 'panel.js', 'style.css')


class Bridge(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, workspace, port=8765):
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(150)

    def log_message(self, *args):
        pass  # Requests may carry local paths; do not write request logs.

    def _send(self, status, data, content_type='application/json; charset=utf-8'):
        payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def _local(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host') == expected

    def do_GET(self):
        if not self._local():
            self._send(403, {'error': '仅允许本机连接。'})
            return
        name = 'index.html' if self.path == '/' else self.path.removeprefix('/')
        if name not in ASSETS:
            self._send(404, {'error': '不存在的页面。'})
            return
        mime = {'index.html': 'text/html', 'panel.js': 'text/javascript', 'style.css': 'text/css'}[name]
        self._send(200, files('lumina.app.assets').joinpath(name).read_bytes(), mime + '; charset=utf-8')

    def do_POST(self):
        if not self._local() or not secrets.compare_digest(self.headers.get('Authorization', '').encode('utf-8'),
                                                         ('Bearer ' + self.server.token).encode('utf-8')):
            self._send(403, {'error': '连接凭据无效，请重新连接本机服务。'})
            return
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
            self._send(403, {'error': '不允许跨站请求。'})
            return
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                raise LuminaError('请求必须是有界 JSON。')
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= 16384:
                raise LuminaError('请求大小无效。')
            data = load_json(self.rfile.read(length), 16384)
            if not isinstance(data, dict):
                raise LuminaError('请求结构无效。')
            workspace = self.server.workspace
            routes = {
                '/api/status': (lambda: {'connected': True, 'provider': workspace.config.provider if workspace.config else None,
                                        'model': workspace.config.model if workspace.config else None}),
                '/api/read': workspace.read,
                '/api/preview': workspace.preview,
                '/api/apply': workspace.apply,
                '/api/history': workspace.history,
                '/api/styles': workspace.styles,
                '/api/save-style': workspace.save_style,
            }
            if self.path not in routes:
                self._send(404, {'error': '不存在的操作。'})
                return
            result = routes[self.path](**data)
            self._send(200, {'result': result})
        except (LuminaError, OSError) as exc:
            self._send(400, {'error': str(exc)})
        except (ValueError, TypeError):
            self._send(400, {'error': '请求字段或类型无效。'})
        except sqlite3.Error:
            self._send(409, {'error': '本地历史存储不可用，请核对当前文件后重试。'})


def run_app(directory, config_path=None, *, port=8765, open_browser=True):
    config = ModelConfig.from_file(config_path) if config_path else None
    workspace = Workspace(directory, config)
    server = Bridge(workspace, port)
    url = f'http://127.0.0.1:{server.server_port}'
    connection = workspace.root / 'connection.json'
    connection.write_text(json.dumps({'url': url, 'token': server.token}), encoding='utf-8')
    print(f'Lumina 本机服务：{url}\nPhotoshop 面板请载入连接文件：{connection}\n按 Ctrl+C 停止。', flush=True)
    if open_browser:
        Timer(.3, partial(webbrowser.open, url + '/#' + server.token)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        # Do not erase a different service's newer connection file.
        try:
            if json.loads(connection.read_text(encoding='utf-8')).get('token') == server.token:
                connection.unlink()
        except (OSError, ValueError):
            pass


def package_plugin(output):
    target = Path(output)
    if target.suffix.lower() != '.zip':
        raise LuminaError('插件开发包必须使用 .zip 后缀。')
    resources = files('lumina.app.assets')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in (*ASSETS, 'manifest.json'):
            archive.writestr(name, resources.joinpath(name).read_bytes())
    return {'plugin_package': str(target.resolve()), 'notice': '解压后通过 Adobe UXP Developer Tool 加载 manifest.json；未签名开发包。'}
