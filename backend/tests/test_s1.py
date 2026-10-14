"""Slice S1 (read the register). Every response is validated against openapi/openapi.yaml."""
import hashlib
import json

import yaml
from fastapi.testclient import TestClient

from backend.app.main import create_app
from .conftest import ROOT

API = "/api/v1"


def test_register_summary_matches_contract_and_gate(client, contract):
    r = client.get(f"{API}/register")
    assert r.status_code == 200
    body = r.json()
    contract.check("RegisterSummary", body)
    assert len(body["obligations"]) == 5
    # Spec pressure test row 1: with no verified_primary reading, nothing may look concluded.
    assert all(o["blocked"] for o in body["obligations"])
    assert all(o["verification_status"] != "verified_primary" for o in body["obligations"])
    assert body["migration"] == {"migrated": 6, "total": 69}


def test_evaluations_are_derived_by_the_checker_not_stored(client):
    doc = yaml.safe_load((ROOT / "eu-ai-act-register.yaml").read_text())
    expected = {e["id"]: e["expected"] for e in doc["evaluations"]}
    views = client.get(f"{API}/register").json()["evaluations"]
    assert len(views) == 4
    for v in views:
        exp = expected[v["evaluation"]["id"]]
        assert v["now"]["completion"] == "blocked_unverified_interpretation"
        assert v["now"] == {k: exp["now"][k] for k in ("completion", "operating_permission", "flags")}
        assert v["if_verified"] == {k: exp["if_verified"][k] for k in ("completion", "operating_permission", "flags")}


def test_obligation_detail(client, contract):
    r = client.get(f"{API}/obligations/OBL-ART50-2")
    assert r.status_code == 200
    body = r.json()
    contract.check("ObligationDetail", body)
    assert body["blocked_reason"] and "verified_primary" in body["blocked_reason"]
    assert {c["id"] for c in body["controls"]} == {"CTL-MARK-PATHS", "CTL-MARK-DETECT"}
    assert body["evaluation_ids"] == ["EVAL-0001"]


def test_control_detail(client, contract):
    r = client.get(f"{API}/controls/CTL-MARK-DETECT")
    assert r.status_code == 200
    contract.check_register_def("control", r.json())
    assert r.json()["category"] == "B"


def test_unknown_ids_are_problem_json(client, contract):
    for url in (f"{API}/obligations/NOPE", f"{API}/controls/NOPE"):
        r = client.get(url)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/problem+json")
        contract.check("Problem", r.json())
        assert r.json()["code"] == "not_found"


def test_baseline_revision_and_export_are_byte_identical(client, contract):
    raw = (ROOT / "eu-ai-act-register.yaml").read_bytes()
    revs = client.get(f"{API}/revisions").json()
    for r in revs:
        contract.check("Revision", r)
    assert revs[0]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert revs[0]["created_at"] is None
    assert client.get(f"{API}/export/register.yaml").content == raw


def test_revision_history_and_diff(tmp_world, contract):
    root, state = tmp_world
    reg = root / "eu-ai-act-register.yaml"
    before = reg.read_bytes()
    b_sha = hashlib.sha256(before).hexdigest()
    after = before.replace(b"Mark outputs in a machine-readable format", b"Mark every output in a machine-readable format")
    assert after != before
    a_sha = hashlib.sha256(after).hexdigest()
    (state / "history" / f"{b_sha}.yaml").write_bytes(before)
    reg.write_bytes(after)
    (state / "receipts" / "p1.json").write_text(json.dumps(
        {"patch_hash": "p1", "revision_before": b_sha, "revision_after": a_sha, "committed_at": "2026-10-14T10:00:00+00:00"}))
    c = TestClient(create_app())
    revs = c.get(f"{API}/revisions").json()
    for r in revs:
        contract.check("Revision", r)
    assert [r["sha256"] for r in revs] == [a_sha, b_sha]
    assert revs[0]["receipt_id"] == "p1" and revs[1]["created_at"] is None
    d = c.get(f"{API}/revisions/{b_sha}/diff/{a_sha}")
    assert d.status_code == 200
    for e in d.json():
        contract.check("DiffEntry", e)
    assert [e["path"] for e in d.json()] == ["obligations[OBL-ART50-2].duty"]
    assert d.json()[0]["op"] == "changed" and "Mark every output" in d.json()[0]["after"]


def test_diff_rejects_malformed_and_unknown_revisions(client, contract):
    bad = client.get(f"{API}/revisions/xyz/diff/abc")
    assert bad.status_code == 422 and bad.json()["code"] == "schema_invalid"
    contract.check("Problem", bad.json())
    ghost = "0" * 64
    missing = client.get(f"{API}/revisions/{ghost}/diff/{ghost}")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


def test_me_is_a_dev_stub_that_refuses_outside_dev(client, contract, monkeypatch):
    r = client.get(f"{API}/me")
    assert r.status_code == 200
    contract.check("User", r.json())
    monkeypatch.setenv("HLRAI_ENV", "pilot")
    r = client.get(f"{API}/me")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    contract.check("Problem", r.json())


def test_contract_validator_actually_rejects_drift(client, contract):
    """Guard against a validator that passes everything."""
    import pytest
    body = client.get(f"{API}/register").json()
    body["obligations"][0]["blocked"] = "yes"
    with pytest.raises(AssertionError):
        contract.check("RegisterSummary", body)
    bad = client.get(f"{API}/controls/CTL-MARK-DETECT").json()
    bad["category"] = "Z"
    with pytest.raises(AssertionError):
        contract.check_register_def("control", bad)
