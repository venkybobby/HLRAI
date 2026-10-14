"""Packets and propose runs (slice S2). Persistence is JSON files under the workflow state dir
(the pipeline already keeps reviews there); Postgres arrives with multi-user writes (spec 4.3).
Models only ever propose: nothing here writes to the register."""
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import stubs
from .errors import ApiError
from .register_store import RegisterStore, value_at, wf

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="propose")
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _read(path: Path):
    return json.loads(path.read_text())


class Runs:
    def __init__(self, store: RegisterStore):
        self.store = store
        self.ws = wf.Workspace(store.root, store.state)
        self.api = store.state / "api"

    # ---- settings
    def mode(self):
        return os.environ.get("HLRAI_MODEL_MODE", "live")

    def settings(self):
        cfg = self.ws.cfg
        lim = cfg["limits"]
        return {"model_mode": self.mode(), "default_drafter": cfg["models"]["drafter"],
                "default_verifier": cfg["models"]["verifier"], "scope_obligation": cfg["scope"]["obligation"],
                "limits": {k: lim[k] for k in ("max_calls", "max_repairs", "max_tokens_per_call",
                                               "max_total_completion_tokens", "max_packet_chars", "max_operations")}}

    # ---- packets
    def create_packet(self, body):
        try:
            packet = wf.load_packet(self.ws, body)
        except ValueError as e:
            raise ApiError(422, "schema_invalid", "Packet rejected", str(e), [str(e)])
        rec = {**packet, "id": uuid.uuid4().hex[:12], "source_hashes": wf.source_hashes(packet), "created_at": _now()}
        _write(self.api / "packets" / f"{rec['id']}.json", rec)
        return rec

    def get_packet(self, pid):
        f = self.api / "packets" / f"{pid}.json"
        if not f.exists():
            raise ApiError(404, "not_found", "Packet not found", f"No packet {pid}")
        return _read(f)

    # ---- models
    def build_models(self, drafter_name, verifier_name):
        if self.mode() == "stub":
            for role, name, table in (("drafter", drafter_name, stubs.DRAFTERS), ("verifier", verifier_name, stubs.VERIFIERS)):
                if not name.startswith("stub:") or name.split(":", 1)[1] not in table:
                    options = ", ".join(f"stub:{n}" for n in table)
                    raise ApiError(422, "schema_invalid", "Unknown stub model", f"Stub {role} must be one of: {options}", [f"{role}_model: {name}"])
            return (wf.StubModel(stubs.drafter(drafter_name.split(":", 1)[1]), drafter_name),
                    wf.StubModel(stubs.verifier(verifier_name.split(":", 1)[1]), verifier_name))
        if drafter_name.startswith("stub:") or verifier_name.startswith("stub:"):
            raise ApiError(422, "schema_invalid", "Stub models are disabled", "Set HLRAI_MODEL_MODE=stub to use stub:<scenario> names")
        m = self.ws.cfg["models"]
        try:
            return (wf.OpenAICompatModel(drafter_name, m["base_url"], m["api_key_env"]),
                    wf.OpenAICompatModel(verifier_name, m["base_url"], m["api_key_env"]))
        except RuntimeError as e:  # missing key; the message names the variable, never a value
            raise ApiError(503, "model_unavailable", "Live models are not configured", str(e))

    # ---- runs
    def start(self, body):
        packet = self.get_packet(body["packet_id"])
        allow_same = bool(body.get("allow_same_model"))
        if body["drafter_model"] == body["verifier_model"] and not allow_same:
            raise ApiError(422, "same_model_refused", "Drafter and verifier are the same model",
                           "Pick two different models, or pass allow_same_model (recorded as a flag).")
        drafter, verifier = self.build_models(body["drafter_model"], body["verifier_model"])
        lim = self.ws.cfg["limits"]
        run = {"id": uuid.uuid4().hex[:12], "packet_id": packet["id"], "status": "running",
               "base_revision": self.store.revision(), "drafter_model": body["drafter_model"],
               "verifier_model": body["verifier_model"], "budget": None, "created_at": _now(), "review_dir": None,
               "_limits": {"max_calls": lim["max_calls"], "max_completion_tokens": lim["max_total_completion_tokens"]}}
        _write(self.api / "runs" / f"{run['id']}.json", run)
        _POOL.submit(self._execute, run["id"], packet, drafter, verifier, allow_same)
        return self._public(run)

    def _execute(self, rid, packet, drafter, verifier, allow_same):
        f = self.api / "runs" / f"{rid}.json"
        try:
            clean = {k: packet[k] for k in ("obligation_id", "sources")}
            review = wf.propose(self.ws, clean, drafter, verifier, allow_same_model=allow_same)
            with _LOCK:
                run = _read(f)
                run.update(status=review["status"], budget=review.get("budget"), review_dir=review["dir"])
                _write(f, run)
        except Exception as e:  # never leave a run stuck in `running`
            with _LOCK:
                run = _read(f)
                run.update(status="escalated", review_dir=None, error=f"{type(e).__name__}: {e}")
                _write(f, run)

    def _public(self, run):
        out = {k: run[k] for k in ("id", "packet_id", "status", "base_revision", "drafter_model", "verifier_model", "created_at")}
        b = run.get("budget")
        if b:
            out["budget"] = {**b, **{"max_calls": run["_limits"]["max_calls"], "max_completion_tokens": run["_limits"]["max_completion_tokens"]}}
        return out

    def list(self, status=None):
        d = self.api / "runs"
        runs = [_read(f) for f in d.glob("*.json")] if d.exists() else []
        runs.sort(key=lambda r: r["created_at"], reverse=True)
        return [self._public(r) for r in runs if status is None or r["status"] == status]

    def get(self, rid):
        f = self.api / "runs" / f"{rid}.json"
        if not f.exists():
            raise ApiError(404, "not_found", "Run not found", f"No run {rid}")
        run = _read(f)
        out = self._public(run)
        out["review"] = self._review(run) if run.get("review_dir") else None
        if run.get("error"):
            out["review"] = {"id": rid, "status": "escalated", "models": {"drafter": run["drafter_model"], "verifier": run["verifier_model"]},
                             "ops": [], "flags": [], "errors": [run["error"]]}
        return out

    def _review(self, run):
        d = Path(run["review_dir"])
        rv = _read(d / "review.json")
        patch = _read(d / "patch.json") if (d / "patch.json").exists() else None
        base = self.ws.plain()
        findings = rv.get("findings") or []
        ops = []
        for i, op in enumerate((patch or {}).get("operations", [])):
            mine = [x for x in findings if x["operation_index"] == i]
            found, before = value_at(base, op["path"])
            o = {"op": op["op"], "path": op["path"], "value": op["value"], "rationale": op.get("rationale", ""),
                 "support": op.get("support", []), "verdict": wf.op_verdict(findings, i) if findings else "unverifiable",
                 "verifier_note": "; ".join(x.get("reason", "") for x in mine if x.get("reason"))}
            if found:
                o["before"] = before
            ops.append(o)
        return {"id": d.name, "status": rv["status"], "patch_hash": rv.get("patch_hash"), "models": rv["models"],
                "ops": ops, "flags": rv.get("flags", []), "errors": rv.get("errors", []),
                "unresolved": rv.get("unresolved", []), "missing_context": rv.get("missing_context", []),
                "notes": rv.get("notes", [])}
