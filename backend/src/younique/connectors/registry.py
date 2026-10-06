from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from younique_sdk import ConnectorManifest

CONNECTOR_KEYS = ("smtp", "gmail", "google_sheets", "google_drive", "http", "webhook")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_module(key: str) -> ModuleType:
    path = repo_root() / "connectors" / key / "manifest.py"
    spec = importlib.util.spec_from_file_location(f"younique_connector_{key}", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifests() -> list[ConnectorManifest]:
    found: list[ConnectorManifest] = []
    for key in CONNECTOR_KEYS:
        module = load_module(key)
        found.append(module.MANIFEST)
    return found


def tools_for_bundles(key: str, enabled_bundles: set[str]) -> list[object]:
    module = load_module(key)
    manifest: ConnectorManifest = module.MANIFEST
    allowed: set[str] = set()
    for bundle in manifest.bundles:
        if bundle.key in enabled_bundles:
            allowed.update(bundle.tools)
    return [tool for tool in module.TOOLS if getattr(tool, "__tool_key__", "") in allowed]
