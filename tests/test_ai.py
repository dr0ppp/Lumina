import base64
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from PIL import Image, PngImagePlugin
import pytest

from lumina.ai import client as transport
from lumina.ai.client import ModelClient, ModelConfig
from lumina.ai.images import prepare_image
from lumina.ai.validation import load_json, validate_proposal
from lumina.ai.workflow import apply_plan, generate_plan, read_plan, save_plan, show_plan
from lumina.cli import main
from lumina.errors import LuminaError
from lumina.xmp import read_parameters

PROPOSAL = {"adjustments": [{"parameter": "Exposure", "value": .45}, {"parameter": "Highlights", "value": -20}],
            "explanation": "人工测试建议，先预览。", "warnings": ["未分析照片。"]}


class FakeModel:
    config = ModelConfig("openai", "test-model", "LUMINA_TEST_KEY")

    def __init__(self, proposal=None):
        self.proposal = deepcopy(PROPOSAL if proposal is None else proposal)
        self.calls = []

    def propose(self, context, text, image):
        self.calls.append((context, text, image))
        return json.dumps(self.proposal)


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"value": NaN}', b'{"value": Infinity}',
    b'```json\n{}\n```', b'{', b'\xff', b'[' * 2000, b' ' * 65537],
    ids=["duplicate", "nan", "infinity", "markdown", "truncated", "encoding", "depth", "size"])
def test_untrusted_json_is_bounded_and_strict(data):
    with pytest.raises(LuminaError):
        load_json(data)


@pytest.mark.parametrize("value", [True, None, "0.5", float("nan"), 5.01, .333, [], {}])
def test_model_numbers_are_not_coerced_or_clamped(value):
    proposal = deepcopy(PROPOSAL)
    proposal["adjustments"][0]["value"] = value
    with pytest.raises(LuminaError):
        validate_proposal(proposal)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "unknown", "extra", "path", "warnings", "explanation"])
def test_invalid_model_structure_fails_whole(mutation):
    data = deepcopy(PROPOSAL)
    if mutation == "empty":
        data["adjustments"] = []
    elif mutation == "duplicate":
        data["adjustments"].append(data["adjustments"][0])
    elif mutation == "unknown":
        data["adjustments"][0]["parameter"] = "Dehaze"
    elif mutation == "extra":
        data["execute"] = "ignored? no"
    elif mutation == "path":
        data["adjustments"][0]["path"] = "other.NEF"
    elif mutation == "warnings":
        data["warnings"] = "not a list"
    else:
        data["explanation"] = "x" * 2001
    with pytest.raises(LuminaError):
        validate_proposal(data)


def test_generation_sends_minimal_context_and_apply_is_offline(make_photo, tmp_path):
    nef, xmp = make_photo()
    before, raw = xmp.read_bytes(), nef.read_bytes()
    client = FakeModel()
    plan, report = generate_plan(nef, "提亮一点", client)
    assert report["can_apply"]
    assert xmp.read_bytes() == before
    context, request, image = client.calls[0]
    assert set(context) == {"parameters", "missing_fields", "process_version", "white_balance"}
    assert str(nef) not in json.dumps(context) and image is None
    target = tmp_path / "test.lumina-plan.json"
    save_plan(target, plan)
    assert read_plan(target) == plan
    preview = show_plan(target)
    assert preview["changes"][0]["before"] == .25 and preview["changes"][0]["after"] == .45
    assert apply_plan(target, dry_run=True)["status"] == "dry_run"
    with pytest.raises(LuminaError, match="expect-plan"):
        apply_plan(target)
    result = apply_plan(target, expected_plan=plan["plan_sha256"])
    assert len(client.calls) == 1
    assert Path(result["backup_path"]).read_bytes() == before
    assert nef.read_bytes() == raw
    assert read_parameters(nef)["parameters"]["Exposure"] == .45
    with pytest.raises(LuminaError, match="预览"):
        apply_plan(target, expected_plan=plan["plan_sha256"])


@pytest.mark.parametrize("change", ["request", "proposal", "path", "hash"])
def test_saved_plan_tampering_never_writes(make_photo, tmp_path, change):
    nef, xmp = make_photo()
    plan, _ = generate_plan(nef, "test", FakeModel())
    before = xmp.read_bytes()
    if change == "request":
        plan["request"] = "different request"
    elif change == "proposal":
        plan["proposal"]["adjustments"][0]["value"] = 3
    elif change == "path":
        plan["nef_path"] = str(tmp_path / "other.NEF")
    else:
        plan["plan_sha256"] = "0" * 64
    target = tmp_path / "tampered.lumina-plan.json"
    target.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(LuminaError):
        apply_plan(target, expected_plan=plan["plan_sha256"])
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))


def test_file_changed_while_model_runs_is_rejected(make_photo):
    nef, xmp = make_photo()
    original = xmp.read_bytes()
    external = original.replace(b'crs:Contrast2012="10"', b'crs:Contrast2012="11"')

    class ConcurrentModel(FakeModel):
        def propose(self, *args):
            xmp.write_bytes(external)
            return super().propose(*args)

    with pytest.raises(LuminaError, match="预览"):
        generate_plan(nef, "test", ConcurrentModel())
    assert xmp.read_bytes() == external


def test_white_balance_and_missing_values_cannot_be_applied(make_photo, tmp_path):
    nef, xmp = make_photo()
    data = deepcopy(PROPOSAL)
    data["adjustments"].append({"parameter": "Temperature", "value": 5000})
    plan, report = generate_plan(nef, "冷一些", FakeModel(data))
    assert not report["can_apply"]
    target = tmp_path / "wb.lumina-plan.json"
    save_plan(target, plan)
    before = xmp.read_bytes()
    with pytest.raises(LuminaError, match="白平衡"):
        apply_plan(target, expected_plan=plan["plan_sha256"])
    assert xmp.read_bytes() == before
    nef, _ = make_photo(attributes={"Exposure2012": None})
    with pytest.raises(LuminaError, match="未记录"):
        generate_plan(nef, "test", FakeModel())


def test_plan_output_never_overwrites_or_uses_photo_extension(make_photo, tmp_path):
    nef, xmp = make_photo()
    plan, _ = generate_plan(nef, "test", FakeModel())
    with pytest.raises(LuminaError):
        save_plan(xmp, plan)
    target = tmp_path / "existing.lumina-plan.json"
    target.write_text("original")
    with pytest.raises(LuminaError):
        save_plan(target, plan)
    assert target.read_text() == "original"


@pytest.mark.parametrize("preview,consent", [("missing.jpg", False), (None, True)])
def test_image_requires_explicit_path_and_consent(make_photo, preview, consent):
    nef, _ = make_photo()
    model = FakeModel()
    with pytest.raises(LuminaError, match="同时"):
        generate_plan(nef, "test", model, preview_path=preview, send_preview=consent)
    assert not model.calls


def test_prepared_image_strips_metadata_and_applies_orientation(tmp_path):
    path = tmp_path / "preview.png"
    source = Image.new("RGB", (1800, 900), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "private author"
    info = PngImagePlugin.PngInfo()
    info.add_text("Secret", "private location")
    source.save(path, exif=exif, pnginfo=info)
    original = path.read_bytes()
    prepared = prepare_image(path)
    decoded = base64.b64decode(prepared.data_url.split(",", 1)[1])
    with Image.open(BytesIO(decoded)) as clean:
        assert clean.size == (800, 1600)
        assert not clean.getexif()
        assert "Secret" not in clean.info
    assert b"private" not in decoded and path.read_bytes() == original


def test_invalid_preview_never_reads_raw_as_image(tmp_path):
    path = tmp_path / "fake.NEF"
    path.write_bytes(b"fake RAW data")
    with pytest.raises(LuminaError):
        prepare_image(path)
    source = tmp_path / "preview.gif"
    Image.new("RGB", (4, 4)).save(source)
    with pytest.raises(LuminaError, match="JPEG/PNG"):
        prepare_image(source)


@pytest.mark.parametrize("kwargs", [
    {"provider": "unknown"}, {"model": "https://other"}, {"api_key_env": "a\nb"},
    {"timeout": True}, {"timeout": 0}, {"max_output_tokens": 999999},
])
def test_config_rejects_bad_fields(kwargs):
    values = {"provider": "openai", "model": "test-model", "api_key_env": "LUMINA_TEST_KEY", **kwargs}
    with pytest.raises(LuminaError):
        ModelConfig(**values)


def test_missing_or_unsafe_key_never_calls_network(monkeypatch):
    monkeypatch.setattr(transport, "_post", lambda *args: pytest.fail("network called"))
    model = ModelClient(FakeModel.config)
    for value in (None, "secret\nheader", "secret\x7fvalue"):
        if value is None:
            monkeypatch.delenv("LUMINA_TEST_KEY", raising=False)
        else:
            monkeypatch.setenv("LUMINA_TEST_KEY", value)
        with pytest.raises(LuminaError):
            model.propose({}, "test")


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_provider_payload_and_response_are_bounded(monkeypatch, provider):
    monkeypatch.setenv("LUMINA_TEST_KEY", "private-test-token")
    calls = []

    def post(url, payload, key, timeout):
        calls.append((url, payload))
        assert key == "private-test-token" and timeout == 60
        assert key not in json.dumps(payload)
        content = json.dumps(PROPOSAL)
        if provider == "openai":
            assert payload["store"] is False
            assert payload["text"]["format"]["strict"]
            return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]}
        assert payload["response_format"] == {"type": "json_object"}
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

    monkeypatch.setattr(transport, "_post", post)
    config = ModelConfig(provider, "test-model", "LUMINA_TEST_KEY")
    assert json.loads(ModelClient(config).propose({}, "test")) == PROPOSAL
    assert len(calls) == 1


@pytest.mark.parametrize("response", [
    {"status": "incomplete"}, {"status": "completed", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
    {"unexpected": "body"}, [],
])
def test_bad_provider_response_is_controlled(monkeypatch, response):
    monkeypatch.setenv("LUMINA_TEST_KEY", "private-test-token")
    monkeypatch.setattr(transport, "_post", lambda *args: response)
    with pytest.raises(LuminaError):
        ModelClient(FakeModel.config).propose({}, "test")


@pytest.mark.parametrize("error", [HTTPError("https://example", 401, "private-test-token", {}, None), URLError("private-test-token"), TimeoutError("private-test-token")])
def test_transport_does_not_echo_error_body_or_retry(monkeypatch, error):
    calls = []

    class Opener:
        def open(self, *args, **kwargs):
            calls.append(1)
            raise error

    monkeypatch.setattr(transport, "build_opener", lambda *args: Opener())
    with pytest.raises(LuminaError) as caught:
        transport._post(transport.ENDPOINTS["openai"], {}, "private-test-token", 1)
    assert "private-test-token" not in str(caught.value)
    assert len(calls) == 1
    assert transport._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other") is None


def test_ai_cli_can_review_and_apply_without_credentials(make_photo, tmp_path, capsys, monkeypatch):
    nef, _ = make_photo()
    plan, _ = generate_plan(nef, "test", FakeModel())
    target = tmp_path / "cli.lumina-plan.json"
    save_plan(target, plan)
    monkeypatch.delenv("LUMINA_TEST_KEY", raising=False)
    assert main(["ai-show", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["plan_sha256"] == plan["plan_sha256"]
    assert main(["ai-apply", str(target), "--expect-plan", plan["plan_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "updated"


def test_cli_request_saves_only_reviewable_plan_and_preflights_destination(make_photo, tmp_path, capsys, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"provider": "openai", "model": "test-model", "api_key_env": "LUMINA_TEST_KEY"}))
    fake = FakeModel()
    monkeypatch.setattr("lumina.cli.ModelClient", lambda config: fake)
    output = tmp_path / "request.lumina-plan.json"
    args = ["ai-plan", str(nef), "test", "--config", str(config), "--output", str(output)]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["saved_plan"] == str(output)
    assert xmp.read_bytes() == before and len(fake.calls) == 1
    assert main(args) == 1
    assert "已存在" in capsys.readouterr().err
    assert len(fake.calls) == 1


def test_config_never_accepts_embedded_key(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"provider": "openai", "model": "test-model", "api_key_env": "TEST", "api_key": "sensitive"}))
    with pytest.raises(LuminaError) as caught:
        ModelConfig.from_file(config)
    assert "sensitive" not in str(caught.value)
    config.write_text('{}')
    with pytest.raises(LuminaError):
        ModelConfig.from_file(config)


def test_save_failure_cleans_only_its_partial_plan(make_photo, tmp_path, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    plan, _ = generate_plan(nef, "test", FakeModel())
    target = tmp_path / "failure.lumina-plan.json"

    def fail(fd):
        raise OSError("simulated full disk")

    monkeypatch.setattr("lumina.ai.workflow.os.fsync", fail)
    with pytest.raises(OSError):
        save_plan(target, plan)
    assert not target.exists() and xmp.read_bytes() == before


def test_explicit_image_preparation_and_no_path_disclosure(make_photo, tmp_path):
    nef, _ = make_photo()
    preview = tmp_path / "private-name.jpg"
    Image.new("RGB", (10, 10), "green").save(preview)
    fake = FakeModel()
    plan, _ = generate_plan(nef, "test", fake, preview_path=preview, send_preview=True)
    assert plan["image_sha256"] == fake.calls[0][2].sha256
    assert str(preview) not in json.dumps(plan)
    fake.config = ModelConfig("deepseek", "test-model", "TEST")
    with pytest.raises(LuminaError, match="仅支持文字"):
        generate_plan(nef, "test", fake, preview_path="nonexistent", send_preview=True)
    assert len(fake.calls) == 1


def test_openai_image_payload_and_sensitive_echo_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LUMINA_TEST_KEY", "private-test-token")
    path = tmp_path / "image.png"
    Image.new("RGB", (4, 4)).save(path)
    prepared = prepare_image(path)

    def post(url, payload, key, timeout):
        assert payload["input"][0]["content"][1]["image_url"] == prepared.data_url
        return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "private-test-token"}]}]}

    monkeypatch.setattr(transport, "_post", post)
    with pytest.raises(LuminaError, match="认证信息"):
        ModelClient(FakeModel.config).propose({}, "test", prepared)
    with pytest.raises(LuminaError, match="认证信息"):
        ModelClient(FakeModel.config).propose({}, "private-test-token")


@pytest.mark.parametrize("oversized", [False, True])
def test_http_success_reads_at_most_one_megabyte(monkeypatch, oversized):
    reads = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            reads.append(size)
            return b" " * size if oversized else b'{"ok": true}'

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == transport.ENDPOINTS["openai"]
            return Response()

    monkeypatch.setattr(transport, "build_opener", lambda *args: Opener())
    if oversized:
        with pytest.raises(LuminaError):
            transport._post(transport.ENDPOINTS["openai"], {}, "dummy", 1)
    else:
        assert transport._post(transport.ENDPOINTS["openai"], {}, "dummy", 1) == {"ok": True}
    assert reads == [1048577]


def test_utf8_size_and_surrogate_input_are_controlled():
    from lumina.ai.validation import text_value
    with pytest.raises(LuminaError):
        load_json('"' + "字" * 25000 + '"')
    with pytest.raises(LuminaError):
        text_value("\ud800", "test", 10)
