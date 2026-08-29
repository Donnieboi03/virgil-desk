"""Config loads exclusively from config/desk.yaml — no duplicated defaults elsewhere."""

from __future__ import annotations

import copy

import pytest
import yaml
from dataclasses import fields

from desk_host.config import (
    config_from_dict,
    config_schema_sections,
    load_config,
    repo_config_path,
)


def test_load_config_matches_desk_yaml(monkeypatch):
    monkeypatch.delenv("DESK_BROWSER_DRIVER", raising=False)
    monkeypatch.delenv("BROWSER_HARNESS_BIN", raising=False)
    monkeypatch.delenv("DESK_HARNESS_BU_NAME", raising=False)
    from desk_host.config import clear_config_cache

    clear_config_cache()
    raw = yaml.safe_load(repo_config_path().read_text(encoding="utf-8"))
    cfg = load_config()
    for section, cls in config_schema_sections():
        expected = raw[section]
        actual = getattr(cfg, section)
        for f in fields(actual):
            assert getattr(actual, f.name) == expected[f.name], f"{section}.{f.name}"


def test_desk_browser_driver_env_override(monkeypatch):
    monkeypatch.setenv("DESK_BROWSER_DRIVER", "extension")
    from desk_host.config import clear_config_cache

    clear_config_cache()
    assert load_config().browser.driver == "extension"


def test_desk_yaml_covers_schema():
    raw = yaml.safe_load(repo_config_path().read_text(encoding="utf-8"))
    for section, cls in config_schema_sections():
        assert section in raw, f"desk.yaml missing section {section}"
        yaml_keys = set(raw[section].keys())
        schema_keys = {f.name for f in fields(cls)}
        assert yaml_keys == schema_keys, f"{section}: yaml/schema key mismatch"


def test_config_from_dict_roundtrip():
    raw = yaml.safe_load(repo_config_path().read_text(encoding="utf-8"))
    cfg = config_from_dict(raw)
    assert cfg.prompts.decompose_items_max == raw["prompts"]["decompose_items_max"]


def test_unknown_yaml_key_rejected(tmp_path):
    raw = yaml.safe_load(repo_config_path().read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    bad["prompts"]["not_a_real_key"] = 99
    with pytest.raises(ValueError, match="unknown keys"):
        config_from_dict(bad)


def test_missing_yaml_key_rejected(tmp_path):
    raw = yaml.safe_load(repo_config_path().read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    del bad["browser"]["scrape_text_max_chars"]
    with pytest.raises(ValueError, match="missing keys"):
        config_from_dict(bad)
