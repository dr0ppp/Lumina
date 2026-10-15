from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
import zipfile

import pytest

from lumina.ai.client import ModelConfig
from lumina.app import workspace as app_module
from lumina.app.server import Bridge, package_plugin
from lumina.app.workspace import Workspace
from lumina.errors import LuminaError
from lumina.xmp import read_parameters


def test_local_application_roundtrip_history_restart_and_relative_style(make_photo, tmp_path):
    nef, xmp = make_photo()
    raw, original = nef.read_bytes(), xmp.read_bytes()
    work = Workspace(tmp_path / 'workspace')
    preview = work.preview(str(nef), '压高光，拉阴影，整体提亮')
    assert xmp.read_bytes() == original
    assert preview['provider'] == 'local'
    work.save_style(preview['id'], '柔和明亮')
    assert work.styles()[0]['name'] == '柔和明亮'
    with pytest.raises(LuminaError, match='先保存并关闭'):
        work.apply(preview['id'], preview['plan_sha256'])
    with pytest.raises(LuminaError, match='摘要'):
        work.apply(preview['id'], 'wrong', closed=True)
    result = work.apply(preview['id'], preview['plan_sha256'], closed=True)
    assert Path(result['backup_path']).read_bytes() == original
    assert nef.read_bytes() == raw
    restarted = Workspace(work.root)
    assert restarted.history(str(nef))[0]['state'] == 'applied'
    with pytest.raises(LuminaError, match='已使用'):
        restarted.apply(preview['id'], preview['plan_sha256'], closed=True)
    next_plan = restarted.preview(str(nef), '', 'style', style='柔和明亮')
    assert next_plan['changes'][0]['before'] == read_parameters(nef)['parameters'][next_plan['changes'][0]['parameter']]
    with pytest.raises(LuminaError, match='已存在'):
        restarted.save_style(preview['id'], '柔和明亮')


def test_stale_and_blocked_proposals_do_not_write(make_photo, tmp_path):
    nef, xmp = make_photo()
    work = Workspace(tmp_path / 'workspace')
    plan = work.preview(str(nef), '曝光设为0.5', 'numeric')
    xmp.write_bytes(xmp.read_bytes().replace(b'+0.25', b'+0.30'))
    current = xmp.read_bytes()
    with pytest.raises(LuminaError):
        work.apply(plan['id'], plan['plan_sha256'], closed=True)
    assert xmp.read_bytes() == current
    plan = work.preview(str(nef), '色温设为5000', 'numeric')
    assert not plan['can_apply']
    with pytest.raises(LuminaError):
        work.apply(plan['id'], plan['plan_sha256'], closed=True)
    with pytest.raises(LuminaError):
        work.save_style(plan['id'], '不支持')
    assert xmp.read_bytes() == current


def test_application_failure_is_durable_and_never_replayed(make_photo, tmp_path, monkeypatch):
    nef, _ = make_photo()
    work = Workspace(tmp_path / 'workspace')
    plan = work.preview(str(nef), '曝光设为0.5', 'numeric')
    def fail(*args, **kwargs):
        raise LuminaError('人工写入故障')
    monkeypatch.setattr(app_module, 'apply_plan', fail)
    with pytest.raises(LuminaError, match='人工'):
        work.apply(plan['id'], plan['plan_sha256'], closed=True)
    assert Workspace(work.root).history()[0]['state'] == 'needs_review'
    with pytest.raises(LuminaError, match='已使用'):
        work.apply(plan['id'], plan['plan_sha256'], closed=True)


def test_interrupted_applying_record_is_not_replayed(make_photo, tmp_path):
    nef, xmp = make_photo()
    work = Workspace(tmp_path / 'workspace')
    plan = work.preview(str(nef), '曝光提高0.2', 'numeric')
    with work.connect() as db:
        db.execute("UPDATE proposals SET state='applying' WHERE id=?", (plan['id'],))
    original = xmp.read_bytes()
    with pytest.raises(LuminaError):
        Workspace(work.root).apply(plan['id'], plan['plan_sha256'], closed=True)
    assert xmp.read_bytes() == original


def test_concurrent_application_only_consumes_once(make_photo, tmp_path):
    nef, _ = make_photo()
    work = Workspace(tmp_path / 'workspace')
    plan = work.preview(str(nef), '曝光提高0.2', 'numeric')
    def apply():
        try:
            return work.apply(plan['id'], plan['plan_sha256'], closed=True)['status']
        except LuminaError:
            return 'rejected'
    with ThreadPoolExecutor(2) as executor:
        assert sorted(executor.map(lambda _: apply(), range(2))) == ['rejected', 'updated']
    assert read_parameters(nef)['parameters']['Exposure'] == .45


def test_ai_requires_explicit_consent_and_config_before_request(make_photo, tmp_path, monkeypatch):
    nef, _ = make_photo()
    work = Workspace(tmp_path / 'workspace')
    with pytest.raises(LuminaError, match='明确同意'):
        work.preview(str(nef), '提亮', 'ai')
    with pytest.raises(LuminaError, match='尚未配置'):
        work.preview(str(nef), '提亮', 'ai', consent=True)
    work.config = ModelConfig('deepseek', 'test', 'LUMINA_TEST')
    calls = []
    def propose(self, context, text, image):
        calls.append(context)
        return json.dumps({'adjustments': [{'parameter': 'Exposure', 'value': .5}], 'explanation': '人工建议', 'warnings': []})
    monkeypatch.setattr(app_module.ModelClient, 'propose', propose)
    plan = work.preview(str(nef), '提亮', 'ai', consent=True)
    work.apply(plan['id'], plan['plan_sha256'], closed=True)
    assert len(calls) == 1
    assert str(nef) not in json.dumps(calls)


@pytest.mark.parametrize('identity', ['../../secret', '', None, 'a'*33])
def test_identity_cannot_escape_workspace(tmp_path, identity):
    with pytest.raises(LuminaError):
        Workspace(tmp_path / 'workspace').apply(identity, 'x', closed=True)


def test_http_auth_origin_host_limits_and_roundtrip(make_photo, tmp_path):
    nef, _ = make_photo()
    server = Bridge(Workspace(tmp_path / 'workspace'), 0)
    thread = Thread(target=server.serve_forever)
    thread.start()
    def request(path, body='{}', *, authenticated=True, extra=None, method='POST'):
        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + server.token
        headers.update(extra or {})
        conn.request(method, path, body.encode('utf-8'), headers)
        response = conn.getresponse()
        status, payload = response.status, response.read()
        conn.close()
        return status, payload
    try:
        assert request('/api/status', authenticated=False)[0] == 403
        assert request('/api/status', extra={'Origin': 'https://evil.example'})[0] == 403
        assert request('/api/status', extra={'Host': 'evil.example'})[0] == 403
        assert request('/api/status', ' '*16385)[0] == 400
        assert request('/api/status', '{"x":1,"x":2}')[0] == 400
        assert request('/api/status', '[]')[0] == 400
        assert request('/api/status', '{"extra":true}')[0] == 400
        assert request('/api/unknown')[0] == 404
        assert request('/../workspace.sqlite3', method='GET')[0] == 404
        status, page = request('/', method='GET')
        assert status == 200 and b'Lumina' in page and server.token.encode() not in page
        status, payload = request('/api/preview', json.dumps({'nef': str(nef), 'text': '曝光设为0.5', 'mode': 'numeric'}))
        assert status == 200
        plan = json.loads(payload)['result']
        assert request('/api/apply', json.dumps({'identity': plan['id'], 'digest': plan['plan_sha256'], 'closed': True}))[0] == 200
        assert read_parameters(nef)['parameters']['Exposure'] == .5
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def test_plugin_package_has_only_declared_ui_assets(tmp_path):
    target = tmp_path / 'plugin.zip'
    package_plugin(target)
    original = sha256(target.read_bytes()).hexdigest()
    with zipfile.ZipFile(target) as z:
        assert set(z.namelist()) == {'index.html', 'panel.js', 'style.css', 'manifest.json'}
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['host']['app'] == 'PS'
        assert manifest['requiredPermissions']['network']['domains'] == ['http://127.0.0.1:8765']
    with pytest.raises(FileExistsError):
        package_plugin(target)
    assert sha256(target.read_bytes()).hexdigest() == original
