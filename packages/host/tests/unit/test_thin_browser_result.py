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
    assert "text_excerpt" not in out["result"]["observe"]


def test_dedupes_nested_observe_eyes_fields():
    payload = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://mail.example/inbox",
            "title": "Inbox",
            "scrape_excerpt": "body",
            "page_tree": "[main] inbox",
            "interact_targets": [
                {"id": 1, "ref": "t1", "kind": "clickable", "label": "Row A", "frame_id": 0}
            ],
            "scroll_containers": [
                {"id": 1, "ref": "s1", "label": "list", "scrollHeight": 10, "clientHeight": 5}
            ],
            "observe": {
                "url": "https://mail.example/inbox",
                "title": "Inbox",
                "text_excerpt": "body",
                "text_omitted": False,
                "excerpt_note": None,
                "page_tree": "[main] inbox DUPLICATE",
                "interact_targets": [
                    {
                        "id": 1,
                        "ref": "t1",
                        "kind": "clickable",
                        "label": "Row A",
                        "text": "fat",
                        "rect": {"x": 0},
                        "frame_id": 0,
                    }
                ],
                "scroll_containers": [{"id": 1, "ref": "s1", "label": "list"}],
                "viewport": {"w": 100, "h": 200},
            },
        },
    }
    out = thin_browser_response(payload)
    result = out["result"]
    assert result["interact_targets"][0]["label"] == "Row A"
    assert result["scrape_excerpt"] == "body"
    assert result["page_tree"] == "[main] inbox"
    obs = result["observe"]
    assert obs["url"] == "https://mail.example/inbox"
    assert obs["title"] == "Inbox"
    assert obs["viewport"] == {"w": 100, "h": 200}
    assert "interact_targets" not in obs
    assert "scroll_containers" not in obs
    assert "page_tree" not in obs
    assert "text_excerpt" not in obs


def test_preserves_eyes_mode_and_hints():
    payload = {
        "ok": True,
        "result": {
            "ok": True,
            "scrape_excerpt": "",
            "eyes_empty": True,
            "eyes_mode": 2,
            "eyes_hints": {"url_path_hint": "login_or_auth"},
            "eyes_settle_ms": 2000,
            "eyes_settle_attempts": 8,
            "page_tree": "[main]",
            "observe": {
                "url": "https://example.com/login",
                "title": "Sign in",
                "text_omitted": False,
                "eyes_mode": 2,
                "eyes_hints": {"url_path_hint": "login_or_auth"},
                "viewport": {"w": 1, "h": 1},
                "device_pixel_ratio": 1,
            },
        },
    }
    out = thin_browser_response(payload)
    result = out["result"]
    assert result["eyes_mode"] == 2
    assert result["eyes_empty"] is True
    assert result["eyes_hints"]["url_path_hint"] == "login_or_auth"
    assert result["eyes_settle_ms"] == 2000
    assert result["page_tree"] == "[main]"
    assert result["observe"]["eyes_mode"] == 2
    assert result["observe"]["eyes_hints"]["url_path_hint"] == "login_or_auth"
