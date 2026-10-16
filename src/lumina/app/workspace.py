"""Durable reviewed proposals, one-shot application and personal styles."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from ..adjustments import _prepare_operations, plan_adjustments
from ..ai.client import ModelClient
from ..ai.validation import text_value
from ..ai.workflow import _digest, apply_plan, generate_plan, save_plan, show_plan
from ..errors import LuminaError
from ..parser.rules import Adjustment
from ..style_adjustments import plan_style
from ..xmp import read_parameters


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Workspace:
    def __init__(self, directory, config=None):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.plans = self.root / 'plans'
        self.plans.mkdir(exist_ok=True)
        self.database = self.root / 'workspace.sqlite3'
        self.config = config
        self.lock = RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, created TEXT NOT NULL, '
                       'state TEXT NOT NULL, review TEXT NOT NULL, result TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS styles (name TEXT PRIMARY KEY, operations TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _path(self, identity):
        if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise LuminaError('方案编号无效。')
        return self.plans / (identity + '.lumina-plan.json')

    def preview(self, nef, text, mode='local', *, consent=False, style=None):
        text_value(nef, '照片路径', 4096)
        with self.lock:
            if mode == 'ai':
                if consent is not True:
                    raise LuminaError('请明确同意发送当前显影参数与需求，再生成 AI 建议。')
                if self.config is None:
                    raise LuminaError('尚未配置模型服务；可先使用本地模式。')
                plan, report = generate_plan(nef, text, ModelClient(self.config))
            else:
                if mode == 'local':
                    report = plan_style(nef, text)
                elif mode == 'numeric':
                    report = plan_adjustments(nef, text)
                elif mode == 'style':
                    text_value(style, '风格名', 80)
                    with self.connect() as db:
                        row = db.execute('SELECT operations FROM styles WHERE name=?', (style,)).fetchone()
                    if row is None:
                        raise LuminaError('个人风格不存在。')
                    operations = tuple(Adjustment(a['parameter'], 'adjust', Decimal(a['value']))
                                       for a in json.loads(row['operations']))
                    report = _prepare_operations(nef, operations)[2]
                    text = '个人风格：' + style
                else:
                    raise LuminaError('未知建议模式。')
                proposal = {'adjustments': [{'parameter': a['parameter'], 'value': a['after']}
                                           for a in report['changes']],
                            'explanation': '本地规则建议，请审核后应用。', 'warnings': report['warnings'][:10]}
                # Use the validated persistent plan format without claiming a model call.
                plan = {'format': 1, 'nef_path': report['nef_path'], 'xmp_path': report['xmp_path'],
                        'original_xmp_sha256': report['original_xmp_sha256'], 'request': text,
                        'provider': 'local', 'model': mode, 'image_sha256': None, 'proposal': proposal}
                plan['plan_sha256'] = _digest(plan)
            identity = uuid4().hex
            path = self._path(identity)
            save_plan(path, plan)
            # Recheck after persistence before presenting any actionable preview.
            report = show_plan(path)
            report.update(id=identity, mode=mode)
            with self.connect() as db:
                db.execute('INSERT INTO proposals VALUES (?,?,?,?,NULL)',
                           (identity, datetime.now(timezone.utc).isoformat(), 'planned', _json(report)))
            return report

    def apply(self, identity, digest, *, closed=False):
        if closed is not True:
            raise LuminaError('请先保存并关闭 ACR 中的照片，再确认应用。')
        path = self._path(identity)
        with self.lock:
            with self.connect() as db:
                row = db.execute('SELECT * FROM proposals WHERE id=?', (identity,)).fetchone()
                if row is None or row['state'] != 'planned':
                    raise LuminaError('该方案已使用或需要人工核对，请重新预览。')
                review = json.loads(row['review'])
                if digest != review['plan_sha256']:
                    raise LuminaError('审核摘要不匹配；请重新预览。')
                # Verify the disk plan is also exactly what the UI reviewed.
                current = show_plan(path)
                if current['plan_sha256'] != digest or not current['can_apply']:
                    raise LuminaError('方案已变化或不可应用；请重新预览。')
                updated = db.execute("UPDATE proposals SET state='applying' WHERE id=? AND state='planned'", (identity,))
                if updated.rowcount != 1:
                    raise LuminaError('方案正在应用，请勿重复提交。')
            # Commit intent before side effects: a crash must never replay a relative adjustment.
            try:
                result = apply_plan(path, expected_plan=digest)
            except (LuminaError, OSError) as exc:
                with self.connect() as db:
                    db.execute("UPDATE proposals SET state='needs_review', result=? WHERE id=?",
                               (_json({'error': str(exc), 'notice': '请核对当前 XMP 和备份，不自动重试。'}), identity))
                raise
            try:
                with self.connect() as db:
                    db.execute("UPDATE proposals SET state='applied', result=? WHERE id=?", (_json(result), identity))
            except sqlite3.Error:
                raise LuminaError('XMP 操作已完成，但历史结果保存失败；请核对照片和备份，不要重复应用。') from None
            return result

    def history(self, nef=None):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM proposals ORDER BY created DESC LIMIT 200').fetchall()
        result = []
        for row in rows:
            review = json.loads(row['review'])
            if nef and str(Path(nef).resolve()) != review['nef_path']:
                continue
            result.append({'id': row['id'], 'created': row['created'], 'state': row['state'],
                           'review': review, 'result': json.loads(row['result']) if row['result'] else None})
        return result

    def save_style(self, identity, name):
        text_value(name, '风格名', 80)
        self._path(identity)
        with self.connect() as db:
            row = db.execute('SELECT review FROM proposals WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise LuminaError('请先生成并审核方案。')
            review = json.loads(row['review'])
            if not review['can_apply']:
                raise LuminaError('不可应用的方案不能保存为风格。')
            operations = [{'parameter': a['parameter'], 'value': str(Decimal(str(a['after'])) - Decimal(str(a['before'])))}
                          for a in review['changes']]
            try:
                db.execute('INSERT INTO styles VALUES (?,?)', (name.strip(), _json(operations)))
            except sqlite3.IntegrityError:
                raise LuminaError('风格名称已存在，请使用新名称。') from None
        return self.styles()

    def styles(self):
        with self.connect() as db:
            return [{'name': row['name'], 'operations': json.loads(row['operations'])}
                    for row in db.execute('SELECT * FROM styles ORDER BY name')]

    def read(self, nef):
        text_value(nef, '照片路径', 4096)
        return read_parameters(nef)
