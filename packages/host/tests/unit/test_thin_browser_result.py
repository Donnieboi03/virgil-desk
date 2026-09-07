"""Unit tests for Hermes-facing browser result thinning."""

from desk_host.thin_browser_result import thin_browser_response


def test_strips_screenshot_base64_keeps_targets_and_act():
    payload = {
        "ok": True,
        "command_id": "c1",
        "result": {
            "command_id": "c1",
            "ok": True,
            "url": "https://example.com/inbox",
            "title": "Inbox",
            "scrape_excerpt": "hello",
            "text_omitted": False,
            "interact_targets": [
                {
                    "id": 1,
                    "ref": "t1",
                    "kind": "clickable",
                    "label": "Apply",
                    "text": "Apply now for the job",
                    "rect": {"x": 1, "y": 2, "w": 3, "h": 4},
                    "center": {"x": 10, "y": 20},
                    "frame_id": 0,
                }
            ],
            "act_resolved": {"op": "click", "used": "target_id"},
            "screenshot": {
                "mime": "image/png",
                "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                "width": 1280,
                "height": 720,
            },
        },
    }
    out = thin_browser_response(payload)
    shot = out["result"]["screenshot"]
    assert shot["omitted"] is True
    assert "base64" not in shot
    assert shot["width"] == 1280
    assert shot["height"] == 720
    tgt = out["result"]["interact_targets"][0]
    assert tgt["ref"] == "t1"
    assert tgt["label"] == "Apply"
    assert tgt["frame_id"] == 0
    assert "text" not in tgt
    assert "rect" not in tgt
    assert "center" not in tgt
    assert out["result"]["act_resolved"]["used"] == "target_id"
    assert out["result"]["scrape_excerpt"] == "hello"
    # Original untouched
    assert "base64" in payload["result"]["screenshot"]
    assert "text" in payload["result"]["interact_targets"][0]

def test_preserves_screenshot_ref_when_present():
    payload = {
        "ok": True,
        "result": {
            "ok": True,
            "screenshot": {"base64": "abc", "width": 10, "height": 10},
            "screenshot_ref": "/tmp/virgil-desk/shot.png",
        },
    }
    out = thin_browser_response(payload)
    assert out["result"]["screenshot"]["omitted"] is True
    assert out["result"]["screenshot"]["screenshot_ref"] == "/tmp/virgil-desk/shot.png"
    assert out["result"]["screenshot_ref"] == "/tmp/virgil-desk/shot.png"
    assert "base64" not in out["result"]["screenshot"]


def test_thins_nested_observe_screenshot():
    payload = {
        "ok": True,
        "result": {
            "ok": True,
            "observe": {
                "url": "https://example.com",
                "text_excerpt": "x",
                "screenshot": {"base64": "zzz", "width": 1, "height": 1},
            },
        },
    }
    out = thin_browser_response(payload)
    assert out["result"]["observe"]["screenshot"]["omitted"] is True
    assert "base64" not in out["result"]["observe"]["screenshot"]
