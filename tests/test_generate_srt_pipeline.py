from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import AudioSegment, GenerateRequest, OcrResult, PageAsset, PanelAsset, QualityReport, SrtTimelineLine, TimelineEntry
from app.routes.generate import _apply_panel_ranges, _build_srt_lines_from_ocr


def test_generate_srt_pipeline_smoke(monkeypatch, tmp_path: Path):
    panel_img = tmp_path / "panel_001.jpg"
    panel_img.write_bytes(b"panel-bytes")

    dirs = {
        "root": tmp_path / "run",
        "pages": tmp_path / "run" / "pages",
        "panels": tmp_path / "run" / "panels",
        "audio": tmp_path / "run" / "audio",
        "clips": tmp_path / "run" / "clips",
        "final": tmp_path / "run" / "final",
        "meta": tmp_path / "run" / "meta",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    def _fake_preflight(_source: str) -> None:
        return None

    def _fake_load_pdf(_src: str, _pages_dir: Path):
        return [PageAsset(page_index=0, image_path=str(tmp_path / "page_000.jpg"), width=100, height=100)]

    def _fake_extract_panels(_page, _panels_dir: Path):
        return [PanelAsset(page_index=0, panel_index=0, image_path=str(panel_img), bbox=(0, 0, 10, 10), confidence=1.0)]

    def _fake_extract_text_batch(_panels):
        return [OcrResult(panel_path=str(panel_img), text="Hello there", confidence=0.98, low_confidence=False)]

    def _fake_generate_voice(_srt_lines, _panel_paths, audio_dir: Path):
        narration = audio_dir / "narration.mp3"
        narration.write_bytes(b"audio")
        seg = AudioSegment(
            line_index=0,
            audio_path=str(narration),
            start_sec=0.0,
            end_sec=2.0,
            duration_sec=2.0,
            pause_sec=0.0,
            provider="elevenlabs",
            voice="v1",
            rendered_text="Hello there.",
        )
        return narration, [seg], [{"type": "voice", "file": str(narration), "start": 0.0, "duration": 2.0, "line_index": 0}], {
            "quality": "cinematic",
            "narration_music_source": "none",
            "narration_music_reason": "disabled",
        }

    def _fake_timeline_from_audio(panels, script_lines, audio):
        _ = audio
        return [
            TimelineEntry(
                panel_path=panels[0].image_path,
                narration=script_lines[0].narration,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
            )
        ]

    def _fake_animate(*_args, **_kwargs):
        out_clip = _args[2]
        out_clip.write_bytes(b"clip")

    def _fake_assemble(clips, narration_path: Path, output_path: Path, subtitles_path=None, bgm_path=None, **kwargs):
        _ = clips, narration_path, subtitles_path, bgm_path, kwargs
        output_path.write_bytes(b"video")
        return output_path

    def _fake_check(_video_path: Path):
        return QualityReport(
            ok=True,
            duration_sec=2.0,
            has_audio=True,
            has_video=True,
            av_delta_sec=0.01,
            checks={"smoke": "ok"},
            warnings=[],
        )

    monkeypatch.setattr("app.routes.generate.run_preflight", _fake_preflight)
    monkeypatch.setattr("app.routes.generate.is_webtoon_url", lambda _x: False)
    monkeypatch.setattr("app.routes.generate.load_pdf", _fake_load_pdf)
    monkeypatch.setattr("app.routes.generate.extract_panels", _fake_extract_panels)
    monkeypatch.setattr("app.routes.generate.extract_text_batch", _fake_extract_text_batch)
    monkeypatch.setattr("app.routes.generate.polish_srt_lines", lambda lines: lines)
    monkeypatch.setattr("app.routes.generate.generate_voice", _fake_generate_voice)
    monkeypatch.setattr("app.routes.generate.build_timeline", _fake_timeline_from_audio)
    monkeypatch.setattr("app.routes.generate.animate_panel", _fake_animate)
    monkeypatch.setattr("app.routes.generate.assemble_video", _fake_assemble)
    monkeypatch.setattr("app.routes.generate.split_video_chunks", lambda source_video, output_dir, max_duration_sec: [])
    monkeypatch.setattr("app.routes.generate.check_video", _fake_check)
    monkeypatch.setattr("app.routes.generate.create_run_dirs", lambda job_id=None: dirs)

    client = TestClient(app)
    res = client.post(
        "/generate",
        json={"pdf_path": "/tmp/input.pdf"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "completed"
    assert payload["quality"] == "cinematic"
    assert payload["audio_path"].endswith("/audio/narration.mp3")
    assert payload["video_path"].endswith("/final/video_youtube.mp4")


def test_generate_pipeline_applies_page_panel_ranges(monkeypatch, tmp_path: Path):
    panel_a = tmp_path / "panel_a.jpg"
    panel_b = tmp_path / "panel_b.jpg"
    panel_c = tmp_path / "panel_c.jpg"
    panel_a.write_bytes(b"a")
    panel_b.write_bytes(b"b")
    panel_c.write_bytes(b"c")

    dirs = {
        "root": tmp_path / "run2",
        "pages": tmp_path / "run2" / "pages",
        "panels": tmp_path / "run2" / "panels",
        "audio": tmp_path / "run2" / "audio",
        "clips": tmp_path / "run2" / "clips",
        "final": tmp_path / "run2" / "final",
        "meta": tmp_path / "run2" / "meta",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    captured = {"panel_paths": []}

    monkeypatch.setattr("app.routes.generate.run_preflight", lambda _source: None)
    monkeypatch.setattr("app.routes.generate.is_webtoon_url", lambda _x: False)
    monkeypatch.setattr(
        "app.routes.generate.load_pdf",
        lambda _src, _pages_dir: [PageAsset(page_index=1, image_path=str(tmp_path / "page_001.jpg"), width=100, height=100)],
    )
    monkeypatch.setattr(
        "app.routes.generate.extract_panels",
        lambda _page, _panels_dir: [
            PanelAsset(page_index=1, panel_index=1, image_path=str(panel_a), bbox=(0, 0, 10, 10), confidence=1.0),
            PanelAsset(page_index=1, panel_index=2, image_path=str(panel_b), bbox=(0, 0, 10, 10), confidence=1.0),
            PanelAsset(page_index=2, panel_index=1, image_path=str(panel_c), bbox=(0, 0, 10, 10), confidence=1.0),
        ],
    )
    monkeypatch.setattr(
        "app.routes.generate.extract_text_batch",
        lambda _panels: [
            OcrResult(panel_path=str(panel_a), text="one", confidence=0.98, low_confidence=False),
            OcrResult(panel_path=str(panel_b), text="two", confidence=0.98, low_confidence=False),
            OcrResult(panel_path=str(panel_c), text="three", confidence=0.98, low_confidence=False),
        ],
    )
    monkeypatch.setattr("app.routes.generate.polish_srt_lines", lambda lines: lines)

    def _fake_generate_voice(_srt_lines, panel_paths, audio_dir: Path):
        captured["panel_paths"] = list(panel_paths)
        narration = audio_dir / "narration.mp3"
        narration.write_bytes(b"audio")
        seg = AudioSegment(
            line_index=0,
            audio_path=str(narration),
            start_sec=0.0,
            end_sec=1.0,
            duration_sec=1.0,
            pause_sec=0.0,
            provider="elevenlabs",
            voice="v1",
            rendered_text="one.",
        )
        return narration, [seg], [{"type": "voice", "file": str(narration), "start": 0.0, "duration": 1.0, "line_index": 0}], {
            "quality": "cinematic",
            "narration_music_source": "none",
            "narration_music_reason": "disabled",
        }

    monkeypatch.setattr("app.routes.generate.generate_voice", _fake_generate_voice)
    monkeypatch.setattr(
        "app.routes.generate.build_timeline",
        lambda panels, script_lines, audio: [
            TimelineEntry(
                panel_path=panels[0].image_path,
                narration=script_lines[0].narration,
                start_sec=0.0,
                end_sec=1.0,
                duration_sec=1.0,
            )
        ],
    )
    monkeypatch.setattr(
        "app.routes.generate.animate_panel",
        lambda *a, **k: a[2].write_bytes(b"clip"),
    )
    monkeypatch.setattr(
        "app.routes.generate.assemble_video",
        lambda clips, narration_path, output_path, subtitles_path=None, bgm_path=None, **kwargs: (
            output_path.write_bytes(b"video"),
            output_path,
        )[1],
    )
    monkeypatch.setattr("app.routes.generate.split_video_chunks", lambda source_video, output_dir, max_duration_sec: [])
    monkeypatch.setattr(
        "app.routes.generate.check_video",
        lambda _video_path: QualityReport(
            ok=True, duration_sec=1.0, has_audio=True, has_video=True, av_delta_sec=0.01, checks={"smoke": "ok"}, warnings=[]
        ),
    )
    monkeypatch.setattr("app.routes.generate.create_run_dirs", lambda job_id=None: dirs)

    client = TestClient(app)
    res = client.post(
        "/generate",
        json={
            "pdf_path": "/tmp/input.pdf",
            "page_from": 1,
            "page_to": 1,
            "panel_from": 2,
            "panel_to": 2,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "completed"
    assert captured["panel_paths"] == [str(panel_b)]


def test_build_srt_lines_from_ocr_uses_empty_for_low_confidence():
    items = [
        OcrResult(panel_path="p1.jpg", text="   ", confidence=0.0, low_confidence=True),
        OcrResult(panel_path="p2.jpg", text="HELLO", confidence=0.95, low_confidence=False),
    ]
    lines = _build_srt_lines_from_ocr(items, fallback_duration=1.5)
    assert lines[0].text == ""
    assert lines[1].text == "HELLO"


def test_generate_pipeline_prefers_provided_srt(monkeypatch, tmp_path: Path):
    panel_img = tmp_path / "panel.jpg"
    panel_img.write_bytes(b"panel")
    dirs = {
        "root": tmp_path / "run3",
        "pages": tmp_path / "run3" / "pages",
        "panels": tmp_path / "run3" / "panels",
        "audio": tmp_path / "run3" / "audio",
        "clips": tmp_path / "run3" / "clips",
        "final": tmp_path / "run3" / "final",
        "meta": tmp_path / "run3" / "meta",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.routes.generate.run_preflight", lambda _source: None)
    monkeypatch.setattr("app.routes.generate.is_webtoon_url", lambda _x: False)
    monkeypatch.setattr(
        "app.routes.generate.load_pdf",
        lambda _src, _pages_dir: [PageAsset(page_index=0, image_path=str(tmp_path / "page.jpg"), width=100, height=100)],
    )
    monkeypatch.setattr(
        "app.routes.generate.extract_panels",
        lambda _page, _panels_dir: [PanelAsset(page_index=0, panel_index=0, image_path=str(panel_img), bbox=(0, 0, 1, 1), confidence=1.0)],
    )
    monkeypatch.setattr(
        "app.routes.generate.extract_text_batch",
        lambda _panels: (_ for _ in ()).throw(AssertionError("OCR should not run when srt_path is provided")),
    )
    monkeypatch.setattr(
        "app.routes.generate.load_srt_timeline",
        lambda _path: [SrtTimelineLine(index=1, start_sec=0.0, end_sec=1.0, text="from srt")],
    )
    monkeypatch.setattr(
        "app.routes.generate.generate_voice",
        lambda _srt, _panel_paths, audio_dir: (
            (audio_dir / "narration.mp3").write_bytes(b"a") or (audio_dir / "narration.mp3"),
            [AudioSegment(line_index=0, audio_path=str(audio_dir / "narration.mp3"), start_sec=0.0, end_sec=1.0, duration_sec=1.0)],
            [{"type": "voice", "file": str(audio_dir / "narration.mp3"), "start": 0.0, "duration": 1.0, "line_index": 0}],
            {"quality": "cinematic", "narration_music_source": "none", "narration_music_reason": "disabled"},
        ),
    )
    monkeypatch.setattr(
        "app.routes.generate.build_timeline",
        lambda panels, script_lines, audio: [
            TimelineEntry(panel_path=panels[0].image_path, narration=script_lines[0].narration, start_sec=0.0, end_sec=1.0, duration_sec=1.0)
        ],
    )
    monkeypatch.setattr(
        "app.routes.generate.animate_panel",
        lambda *a, **k: a[2].write_bytes(b"clip"),
    )
    monkeypatch.setattr(
        "app.routes.generate.assemble_video",
        lambda clips, narration_path, output_path, subtitles_path=None, bgm_path=None, **kwargs: (
            output_path.write_bytes(b"video"),
            output_path,
        )[1],
    )
    monkeypatch.setattr("app.routes.generate.split_video_chunks", lambda source_video, output_dir, max_duration_sec: [])
    monkeypatch.setattr(
        "app.routes.generate.check_video",
        lambda _video_path: QualityReport(
            ok=True, duration_sec=1.0, has_audio=True, has_video=True, av_delta_sec=0.0, checks={"ok": True}, warnings=[]
        ),
    )
    monkeypatch.setattr("app.routes.generate.create_run_dirs", lambda job_id=None: dirs)

    client = TestClient(app)
    res = client.post("/generate", json={"pdf_path": "/tmp/in.pdf", "srt_path": "/tmp/in.srt"})
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_apply_panel_range_uses_global_ordinal_after_page_filter():
    panels = [
        PanelAsset(page_index=1, panel_index=1, image_path="p1", bbox=(0, 0, 1, 1), confidence=1.0),
        PanelAsset(page_index=1, panel_index=2, image_path="p2", bbox=(0, 0, 1, 1), confidence=1.0),
        PanelAsset(page_index=2, panel_index=1, image_path="p3", bbox=(0, 0, 1, 1), confidence=1.0),
        PanelAsset(page_index=2, panel_index=2, image_path="p4", bbox=(0, 0, 1, 1), confidence=1.0),
    ]
    req = GenerateRequest(pdf_path="/tmp/x.pdf", panel_from=2, panel_to=3)
    selected, meta = _apply_panel_ranges(panels, req)
    assert [p.image_path for p in selected] == ["p2", "p3"]
    assert meta["selected_panels"] == 2