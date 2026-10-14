import shutil
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.main import create_app  # noqa: E402

CONTRACT = ROOT / "openapi" / "openapi.yaml"
REGISTER_SCHEMA = ROOT / "eu-ai-act-register.schema.json"
BASE = CONTRACT.as_uri()


class Contract:
    """Validates a response body against a named schema in openapi/openapi.yaml, including
    $refs into eu-ai-act-register.schema.json (one source of truth, spec 6.1 rule 1)."""

    def __init__(self):
        import json
        spec = yaml.safe_load(CONTRACT.read_text())
        reg = Registry().with_resources([
            (BASE, Resource.from_contents(spec, DRAFT202012)),
            (REGISTER_SCHEMA.as_uri(), Resource.from_contents(json.loads(REGISTER_SCHEMA.read_text()), DRAFT202012)),
        ])
        self.registry = reg
        self.spec = spec

    def check(self, name, body):
        v = Draft202012Validator({"$ref": f"{BASE}#/components/schemas/{name}"}, registry=self.registry)
        errs = sorted(v.iter_errors(body), key=lambda e: list(e.path))
        assert not errs, f"{name} violates contract: " + "; ".join(f"{list(e.path)}: {e.message[:120]}" for e in errs[:5])

    def check_register_def(self, name, body):
        v = Draft202012Validator({"$ref": f"{REGISTER_SCHEMA.as_uri()}#/$defs/{name}"}, registry=self.registry)
        errs = list(v.iter_errors(body))
        assert not errs, f"register def {name} violated: {errs[0].message[:160]}"


@pytest.fixture(scope="session")
def contract():
    return Contract()


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def tmp_world(tmp_path, monkeypatch):
    """A scratch root (register copy) and state dir so history/receipt tests never touch the repo."""
    shutil.copy(ROOT / "eu-ai-act-register.yaml", tmp_path / "eu-ai-act-register.yaml")
    state = tmp_path / ".state"
    for d in ("history", "receipts"):
        (state / d).mkdir(parents=True)
    monkeypatch.setenv("HLRAI_ROOT", str(tmp_path))
    monkeypatch.setenv("HLRAI_STATE", str(state))
    return tmp_path, state
