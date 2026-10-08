"""Drafter -> deterministic checks -> Verifier -> human approval -> idempotent commit.

Scope: one obligation (see workflow_config.json). Models only PROPOSE and REVIEW.
Everything that decides (paths, quotes, hashes, approval, commit) is plain code.
"""
import argparse
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

sys.path.insert(0, str(Path(__file__).parent))
from models import (Budget, BudgetExceeded, Metered, OpenAICompatModel, StubModel,  # noqa: E402
                    extract_json)
import prompts  # noqa: E402

HERE = Path(__file__).resolve().parent
REGISTER = "eu-ai-act-register.yaml"
VERDICTS = {"supported", "contradicted", "unverifiable"}
SEG = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[([A-Za-z0-9_\-]+)\])?$")


# ---------- small helpers ----------
def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def to_plain(o):
    return json.loads(json.dumps(o, default=str))


def make_yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(type(None), lambda s, d: s.represent_scalar("tag:yaml.org,2002:null", "null"))
    return y


def atomic_write(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode())
    os.replace(tmp, path)


class Workspace:
    """root holds the register, schema and checker; state holds everything the workflow writes."""

    def __init__(self, root, state=None, config=None):
        self.root = Path(root)
        self.state = Path(state) if state else self.root / ".workflow-state"
        self.cfg = config if config is not None else json.loads((HERE / "workflow_config.json").read_text())
        for d in ("reviews", "approvals", "receipts", "history", "intents"):
            (self.state / d).mkdir(parents=True, exist_ok=True)

    @property
    def register(self):
        return self.root / REGISTER

    def revision(self):
        return sha(self.register.read_bytes())

    def plain(self):
        return to_plain(make_yaml().load(self.register.read_text()))


# ---------- path handling ----------
def parse_path(path):
    segs = []
    for s in path.split("."):
        m = SEG.match(s)
        if not m:
            raise ValueError(f"bad path segment {s!r}")
        segs.append((m.group(1), m.group(2)))
    return segs


def resolve_parent(doc, path):
    """Return (container, key) so container[key] is the target. Raises if any step is missing."""
    segs = parse_path(path)
    cur = doc
    for i, (name, ident) in enumerate(segs):
        last = i == len(segs) - 1
        if ident is not None:
            lst = cur.get(name) if isinstance(cur, dict) else None
            if not isinstance(lst, list):
                raise KeyError(f"{name} is not a list")
            hit = [x for x in lst if isinstance(x, dict) and x.get("id") == ident]
            if len(hit) != 1:
                raise KeyError(f"{name}[{ident}] not found")
            if last:
                raise KeyError("path may not end on a whole record")
            cur = hit[0]
        else:
            if not isinstance(cur, dict) or name not in cur:
                raise KeyError(f"{name} not found")
            if last:
                return cur, name
            cur = cur[name]
    raise KeyError("empty path")


def path_allowed(path, allowed):
    return any(path == a or path.startswith(a + ".") or path.startswith(a + "[") for a in allowed)


def diff_paths(a, b, prefix=""):
    """Paths that differ. Lists of id-keyed dicts are compared per id; other lists as a whole."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out += diff_paths(a[k], b[k], p)
        return out
    if (isinstance(a, list) and isinstance(b, list) and a and b
            and all(isinstance(x, dict) and "id" in x for x in a + b)
            and len({x["id"] for x in a}) == len(a) and len({x["id"] for x in b}) == len(b)):
        out = []
        ia, ib = {x["id"]: x for x in a}, {x["id"]: x for x in b}
        key = prefix
        for i in sorted(set(ia) | set(ib)):
            p = f"{key}[{i}]"
            if i not in ia or i not in ib:
                out.append(p)
            else:
                out += diff_paths(ia[i], ib[i], p)
        return out
    return [] if a == b else [prefix]


def covered(changed, op_paths):
    """Every changed path must sit at or below an operation path."""
    return all(any(c == o or c.startswith(o + ".") or c.startswith(o + "[") for o in op_paths) for c in changed)


# ---------- sources, quotes, hashing ----------
def source_hashes(packet):
    return {s["source_id"]: sha(s["text"]) for s in packet["sources"]}


def patch_hash(patch):
    return sha(canon({"base_revision": patch["base_revision"], "source_hashes": patch["source_hashes"],
                      "operations": patch["operations"]}))


def check_support(support, sources, window):
    """Every item must name a real source, a locator found in it, and a quote at/after the locator."""
    errs = []
    if not isinstance(support, list) or not support:
        return ["no support items"]
    for k, s in enumerate(support):
        if not isinstance(s, dict):
            errs.append(f"support[{k}] is not an object")
            continue
        text = sources.get(s.get("source_id"))
        loc, q = s.get("locator"), s.get("quote")
        if text is None:
            errs.append(f"support[{k}]: unknown source_id {s.get('source_id')!r}")
        elif not isinstance(loc, str) or not loc or not isinstance(q, str) or not q:
            errs.append(f"support[{k}]: locator and quote must be non-empty strings")
        else:
            ok = False
            start = text.find(loc)
            while start != -1 and not ok:
                ok = q in text[start:start + len(loc) + window]
                start = text.find(loc, start + 1)
            if not ok:
                errs.append(f"support[{k}]: locator/quote not found verbatim in {s['source_id']} (within {window} chars)")
    return errs


# ---------- packet ----------
def load_packet(ws, packet):
    lim = ws.cfg["limits"]
    if not isinstance(packet, dict) or packet.get("obligation_id") != ws.cfg["scope"]["obligation"]:
        raise ValueError(f"packet must be for {ws.cfg['scope']['obligation']}")
    srcs = packet.get("sources")
    if not isinstance(srcs, list) or not srcs or not all(
            isinstance(s, dict) and isinstance(s.get("source_id"), str) and isinstance(s.get("text"), str) for s in srcs):
        raise ValueError("packet.sources must be a non-empty list of {source_id, text}")
    if len({s["source_id"] for s in srcs}) != len(srcs):
        raise ValueError("duplicate source_id")
    if sum(len(s["text"]) for s in srcs) > lim["max_packet_chars"]:
        raise ValueError(f"packet exceeds {lim['max_packet_chars']} characters; no model call was made")
    return packet


def scoped_records(ws, doc):
    oid = ws.cfg["scope"]["obligation"]
    obl = next(o for o in doc["obligations"] if o["id"] == oid)
    ctls = [c for c in doc["controls"] if c["id"] in obl.get("controls", [])]
    return {"obligation": obl, "controls": ctls}


# ---------- patch validation ----------
def apply_ops(doc, ops):
    for op in ops:
        parent, key = resolve_parent(doc, op["path"])
        parent[key] = copy.deepcopy(op["value"])
    return doc


def run_checker(ws, doc_plain):
    """Schema + behaviour checker on a temp copy. Returns (ok, tail)."""
    tmp = ws.state / "check-tmp.yaml"
    y = make_yaml()
    buf = io.StringIO()
    y.dump(doc_plain, buf)
    tmp.write_text(buf.getvalue())
    r = subprocess.run([sys.executable, str(ws.root / "check_register.py"), "--register", str(tmp), "--no-report"],
                       cwd=ws.root, capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
    return r.returncode == 0, fails[:5] or r.stderr.strip().splitlines()[-3:]


def validate_patch(ws, patch, packet, run_check=True):
    """All deterministic checks. Returns a list of error strings (empty = valid)."""
    cfg, lim = ws.cfg, ws.cfg["limits"]
    errs = []
    if not isinstance(patch, dict) or not isinstance(patch.get("operations"), list):
        return ["patch must be an object with an operations list"]
    base_doc = ws.plain()
    if patch.get("base_revision") != ws.revision():
        errs.append("base_revision does not match the current register")
    if patch.get("source_hashes") != source_hashes(packet):
        errs.append("source_hashes do not match the supplied sources")
    ops = patch["operations"]
    if len(ops) > lim["max_operations"]:
        errs.append(f"more than {lim['max_operations']} operations")
        return errs
    sources = {s["source_id"]: s["text"] for s in packet["sources"]}
    seen = set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or op.get("op") != "replace" or not isinstance(op.get("path"), str) or "value" not in op:
            errs.append(f"op {i}: must be {{op: replace, path, value, support}}")
            continue
        if op["path"] in seen:
            errs.append(f"op {i}: duplicate path")
        seen.add(op["path"])
        if not path_allowed(op["path"], cfg["allowed_paths"]):
            errs.append(f"op {i}: path {op['path']} is not allowed")
            continue
        try:
            resolve_parent(base_doc, op["path"])
        except (KeyError, ValueError) as e:
            errs.append(f"op {i}: {e}")
            continue
        errs += [f"op {i}: {e}" for e in check_support(op.get("support"), sources, lim["locator_window_chars"])]
    if errs:
        return errs
    after = apply_ops(copy.deepcopy(base_doc), ops)
    changed = diff_paths(base_doc, after)
    if not covered(changed, [o["path"] for o in ops]):
        errs.append("applying the patch changes paths outside the declared operations")
    if run_check:
        ok, tail = run_checker(ws, after)
        if not ok:
            errs.append("register schema/checker fails after applying the patch: " + " | ".join(tail))
    return errs


# ---------- deterministic flags ----------
def compute_flags(ws, patch, drafter_name, verifier_name):
    flags = []
    base = ws.plain()
    for i, op in enumerate(patch["operations"]):
        p = op["path"]
        if ".requirements" in p:
            try:
                parent, key = resolve_parent(base, p)
                old = {r["id"]: r for r in parent[key]}
            except KeyError:
                old = {}
            for r in op["value"] if isinstance(op["value"], list) else []:
                o = old.get(r.get("id"))
                if r.get("legal_status") == "binding_law" and (o is None or o.get("legal_status") != "binding_law"):
                    flags.append({"flag": "binding_upgrade", "op": i,
                                  "detail": f"{r.get('id')}: {o.get('legal_status') if o else 'new'} -> binding_law"})
        if ".effective" in p:
            flags.append({"flag": "date_change", "op": i, "detail": p})
    if drafter_name == verifier_name:
        flags.append({"flag": "same_model", "op": None, "detail": f"drafter and verifier are both {drafter_name}"})
    return flags


# ---------- model calls ----------
def drafter_request(ws, packet, base_rev, hashes, errors=None, previous=None):
    doc = ws.plain()
    req = {
        "task": "Propose the smallest set of replace operations the sources support. Return no operations if they do not.",
        "base_revision": base_rev, "source_hashes": hashes,
        "allowed_paths": ws.cfg["allowed_paths"],
        "current_records": scoped_records(ws, doc),
        "sources": packet["sources"],
        "output_schema": prompts.DRAFTER_SCHEMA_HINT,
    }
    if errors:
        req["previous_attempt"] = previous
        req["validation_errors_to_fix"] = errors
    return json.dumps(req, ensure_ascii=False)


def verifier_request(ws, packet, patch, phash):
    return json.dumps({
        "task": "Review each operation. Give one finding per operation_index.",
        "patch_hash": phash, "operations": patch["operations"],
        "current_records": scoped_records(ws, ws.plain()),
        "sources": packet["sources"],
        "output_schema": prompts.VERIFIER_SCHEMA_HINT,
    }, ensure_ascii=False)


def validate_findings(raw, patch, phash, packet, window):
    """Returns (clean_findings, notes) or raises ValueError. Unsupported 'supported' is downgraded."""
    if not isinstance(raw, dict) or raw.get("patch_hash") != phash:
        raise ValueError("verifier patch_hash missing or wrong")
    fs = raw.get("findings")
    if not isinstance(fs, list):
        raise ValueError("findings must be a list")
    sources = {s["source_id"]: s["text"] for s in packet["sources"]}
    by = {}
    for f in fs:
        if not isinstance(f, dict) or f.get("verdict") not in VERDICTS or not isinstance(f.get("operation_index"), int):
            raise ValueError("finding malformed or verdict not in supported/contradicted/unverifiable")
        by.setdefault(f["operation_index"], []).append(f)
    missing = [i for i in range(len(patch["operations"])) if i not in by]
    if missing:
        raise ValueError(f"verifier did not cover operations {missing}")
    notes, clean = [], []
    for i in range(len(patch["operations"])):
        for f in by[i]:
            f = dict(f)
            if f["verdict"] == "supported":
                e = check_support(f.get("support"), sources, window)
                if e:
                    f["verdict"] = "unverifiable"
                    f["reason"] = (f.get("reason") or "") + " [downgraded: supported without a quote found in the sources: " + "; ".join(e) + "]"
                    notes.append(f"op {i} downgraded")
            clean.append(f)
    return clean, notes


def op_verdict(findings, i):
    vs = {f["verdict"] for f in findings if f["operation_index"] == i}
    return "contradicted" if "contradicted" in vs else "unverifiable" if "unverifiable" in vs or not vs else "supported"


# ---------- propose ----------
def propose(ws, packet, drafter, verifier, allow_same_model=False):
    lim = ws.cfg["limits"]
    packet = load_packet(ws, packet)  # raises before any model call
    budget = Budget(lim["max_calls"], lim["max_total_completion_tokens"], lim["max_tokens_per_call"])
    temp = ws.cfg["models"]["temperature"]
    D, V = Metered(drafter, budget, temp), Metered(verifier, budget, temp)
    base_rev, hashes = ws.revision(), source_hashes(packet)
    review = {"created_at": now(), "base_revision": base_rev, "source_hashes": hashes, "models":
              {"drafter": D.name, "verifier": V.name}, "status": None, "errors": [], "flags": [], "findings": [],
              "unresolved": [], "missing_context": [], "notes": []}
    if D.name == V.name and not allow_same_model:
        raise ValueError("drafter and verifier are the same model; pass allow_same_model to proceed (recorded as a flag)")
    patch, errors, prev = None, None, None
    try:
        for attempt in range(lim["max_repairs"] + 1):
            text = D.chat(prompts.DRAFTER_SYSTEM, drafter_request(ws, packet, base_rev, hashes, errors, prev))
            try:
                cand = extract_json(text)
            except ValueError as e:
                errors, prev = [str(e)], None
                continue
            cand.setdefault("base_revision", base_rev)
            cand.setdefault("source_hashes", hashes)
            review["unresolved"] = cand.get("unresolved") or []
            if cand.get("operations") == []:
                patch = cand
                errors = None
                break
            errors = validate_patch(ws, cand, packet)
            prev = cand.get("operations")
            if not errors:
                patch = cand
                break
        review["repairs_used"] = attempt
        if patch is None:
            review["status"], review["errors"] = "escalated", errors or ["no valid patch"]
            return finish(ws, review, packet, None, budget)
        patch = {"base_revision": patch["base_revision"], "source_hashes": patch["source_hashes"],
                 "operations": patch["operations"], "unresolved": review["unresolved"]}
        if not patch["operations"]:
            review["status"] = "no_change"
            return finish(ws, review, packet, patch, budget)
        phash = patch_hash(patch)
        review["patch_hash"] = phash
        review["flags"] = compute_flags(ws, patch, D.name, V.name)
        findings = None
        for _ in range(2):
            vt = V.chat(prompts.VERIFIER_SYSTEM, verifier_request(ws, packet, patch, phash))
            try:
                raw = extract_json(vt)
                findings, notes = validate_findings(raw, patch, phash, packet, lim["locator_window_chars"])
                review["notes"] += notes
                mc = raw.get("missing_context")
                review["missing_context"] = [str(x) for x in mc] if isinstance(mc, list) else []
                break
            except ValueError as e:
                review["errors"].append(f"verifier output rejected: {e}")
        if findings is None:
            review["status"] = "verifier_invalid"
            return finish(ws, review, packet, patch, budget)
        review["findings"] = findings
        review["status"] = ("ready_for_review"
                            if all(op_verdict(findings, i) == "supported" for i in range(len(patch["operations"])))
                            else "needs_revision")
    except BudgetExceeded as e:
        review["status"], review["errors"] = "budget_exceeded", review["errors"] + [str(e)]
    return finish(ws, review, packet, patch, budget)


def finish(ws, review, packet, patch, budget=None):
    review["budget"] = budget.summary() if budget else None
    d = ws.state / "reviews" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{(review.get('patch_hash') or 'nopatch')[:8]}"
    d.mkdir(parents=True)
    (d / "packet.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False))
    if patch is not None:
        (d / "patch.json").write_text(json.dumps(patch, indent=2, ensure_ascii=False))
    (d / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False))
    (d / "review.md").write_text(render_md(ws, review, patch))
    review["dir"] = str(d)
    return review


def render_md(ws, r, patch):
    L = [f"# Review: {r['status']}", "", f"- Models: drafter `{r['models']['drafter']}`, verifier `{r['models']['verifier']}`",
         f"- Base revision: `{r['base_revision'][:12]}`", f"- Patch hash: `{r.get('patch_hash', '-')}`"]
    if r["errors"]:
        L += ["", "## Errors"] + [f"- {e}" for e in r["errors"]]
    if r["flags"]:
        L += ["", "## Flags (each must be acknowledged to approve)"] + [f"- **{f['flag']}** op {f['op']}: {f['detail']}" for f in r["flags"]]
    if patch and patch["operations"]:
        base = ws.plain()
        L += ["", "## Operations"]
        for i, op in enumerate(patch["operations"]):
            try:
                p, k = resolve_parent(base, op["path"])
                old = p[k]
            except KeyError:
                old = "?"
            L += [f"### {i}. `{op['path']}`", f"- Old: `{json.dumps(old, ensure_ascii=False)}`",
                  f"- New: `{json.dumps(op['value'], ensure_ascii=False)}`", f"- Rationale (drafter): {op.get('rationale', '')}"]
            L += [f"- Quote [{s['source_id']}]: \"{s['quote']}\"" for s in op.get("support", [])]
            for f in r["findings"]:
                if f["operation_index"] == i:
                    L.append(f"- Verifier **{f['verdict']}**: {f.get('reason', '')}")
    for key, title in (("unresolved", "Unresolved (drafter)"), ("missing_context", "Missing context (verifier)")):
        if r.get(key):
            L += ["", f"## {title}"] + [f"- {x}" for x in r[key]]
    L += ["", "Models propose and review. Verification status stays unchanged; raising it to verified_primary is a separate human act."]
    return "\n".join(L) + "\n"


# ---------- approve / commit ----------
class Refused(Exception):
    pass


def approve(ws, review_dir, reviewer, hash_prefix, acknowledge=()):
    d = Path(review_dir)
    review = json.loads((d / "review.json").read_text())
    if review["status"] != "ready_for_review":
        raise Refused(f"review status is {review['status']}; only ready_for_review can be approved")
    if reviewer not in ws.cfg["approvers"]:
        raise Refused(f"{reviewer!r} is not an authorised approver")
    ph = review["patch_hash"]
    if len(hash_prefix) < 8 or not ph.startswith(hash_prefix):
        raise Refused("typed patch hash prefix (8+ characters) does not match")
    patch = json.loads((d / "patch.json").read_text())
    if patch_hash(patch) != ph:
        raise Refused("patch.json no longer matches its recorded hash")
    need = {f["flag"] for f in review["flags"]}
    if need - set(acknowledge):
        raise Refused(f"unacknowledged flags: {sorted(need - set(acknowledge))}")
    rec = {"patch_hash": ph, "review_dir": str(d), "reviewer": reviewer, "approved_at": now(),
           "base_revision": patch["base_revision"], "source_hashes": patch["source_hashes"],
           "acknowledged": sorted(need), "models": review["models"]}
    f = ws.state / "approvals" / f"{ph}.json"
    f.write_text(json.dumps(rec, indent=2))
    return str(f)


def to_ruamel(v, in_list=False):
    if isinstance(v, dict):
        m = CommentedMap((k, to_ruamel(x)) for k, x in v.items())
        if in_list and all(not isinstance(x, (dict, list)) for x in v.values()):
            m.fa.set_flow_style()
        return m
    if isinstance(v, list):
        s = CommentedSeq(to_ruamel(x, True) for x in v)
        if all(not isinstance(x, (dict, list)) for x in v):
            s.fa.set_flow_style()
        return s
    return v


def commit(ws, approval_file):
    ap = json.loads(Path(approval_file).read_text())
    ph = ap["patch_hash"]
    receipt = ws.state / "receipts" / f"{ph}.json"
    if receipt.exists():
        return {"result": "already_committed", "receipt": str(receipt)}
    d = Path(ap["review_dir"])
    patch = json.loads((d / "patch.json").read_text())
    packet = json.loads((d / "packet.json").read_text())
    if patch_hash(patch) != ph:
        raise Refused("patch does not match the approved hash")
    if ap["reviewer"] not in ws.cfg["approvers"]:
        raise Refused("approver is no longer authorised")
    if source_hashes(packet) != ap["source_hashes"] or patch["source_hashes"] != ap["source_hashes"]:
        raise Refused("source hashes differ from those approved")
    intent = ws.state / "intents" / f"{ph}.json"
    cur = ws.revision()
    if intent.exists() and cur == json.loads(intent.read_text())["expected_after_revision"]:
        return write_receipt(ws, ap, patch, None, cur, recovered=True)
    if cur != ap["base_revision"]:
        raise Refused("register changed since approval (stale base revision); re-run propose")
    errs = validate_patch(ws, patch, packet)
    if errs:
        raise Refused("re-validation failed: " + "; ".join(errs))
    y = make_yaml()
    doc = y.load(ws.register.read_text())
    apply_ops_ruamel(doc, patch["operations"])
    buf = io.StringIO()
    y.dump(doc, buf)
    new_bytes = buf.getvalue().encode()
    expected_plain = apply_ops(ws.plain(), patch["operations"])
    if to_plain(make_yaml().load(new_bytes.decode())) != expected_plain:
        raise Refused("round-trip changed content beyond the patch; nothing written")
    after = sha(new_bytes)
    intent.write_text(json.dumps({"expected_after_revision": after, "at": now()}))
    hist = ws.state / "history" / f"{cur}.yaml"
    if not hist.exists():
        hist.write_bytes(ws.register.read_bytes())
    atomic_write(ws.register, new_bytes)
    return write_receipt(ws, ap, patch, cur, after)


def apply_ops_ruamel(doc, ops):
    for op in ops:
        parent, key = resolve_parent(doc, op["path"])
        parent[key] = to_ruamel(op["value"])


def write_receipt(ws, ap, patch, before, after, recovered=False):
    r = {"patch_hash": ap["patch_hash"], "approved_by": ap["reviewer"], "approved_at": ap["approved_at"],
         "committed_at": now(), "revision_before": before or ap["base_revision"], "revision_after": after,
         "paths": [o["path"] for o in patch["operations"]], "models": ap["models"],
         "acknowledged_flags": ap["acknowledged"], "recovered_after_interruption": recovered}
    f = ws.state / "receipts" / f"{ap['patch_hash']}.json"
    f.write_text(json.dumps(r, indent=2))
    return {"result": "committed" if not recovered else "recovered", "receipt": str(f)}


# ---------- CLI ----------
def build_models(ws, args):
    if args.stub:
        s = json.loads(Path(args.stub).read_text())
        return StubModel(s["drafter"], "stub-drafter"), StubModel(s["verifier"], "stub-verifier")
    m = ws.cfg["models"]
    dn, vn = args.drafter_model or m["drafter"], args.verifier_model or m["verifier"]
    if not dn or not vn:
        sys.exit("live mode needs --drafter-model and --verifier-model (no model names are assumed)")
    return (OpenAICompatModel(dn, m["base_url"], m["api_key_env"]), OpenAICompatModel(vn, m["base_url"], m["api_key_env"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(HERE.parent))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--packet", required=True)
    p.add_argument("--stub", help="JSON file {drafter:[...], verifier:[...]} of scripted replies")
    p.add_argument("--live", action="store_true")
    p.add_argument("--drafter-model")
    p.add_argument("--verifier-model")
    p.add_argument("--allow-same-model", action="store_true")
    a = sub.add_parser("approve")
    a.add_argument("--review", required=True)
    a.add_argument("--reviewer", required=True)
    a.add_argument("--patch-hash", required=True)
    a.add_argument("--acknowledge", nargs="*", default=[])
    c = sub.add_parser("commit")
    c.add_argument("--approval", required=True)
    args = ap.parse_args(argv)
    ws = Workspace(args.root)
    try:
        if args.cmd == "propose":
            if bool(args.stub) == bool(args.live):
                sys.exit("choose exactly one of --stub or --live")
            d, v = build_models(ws, args)
            r = propose(ws, json.loads(Path(args.packet).read_text()), d, v, args.allow_same_model)
            print(r["status"], r["dir"])
            print((Path(r["dir"]) / "review.md").read_text())
        elif args.cmd == "approve":
            print(approve(ws, args.review, args.reviewer, args.patch_hash, args.acknowledge))
        else:
            print(json.dumps(commit(ws, args.approval), indent=2))
    except (Refused, ValueError, RuntimeError) as e:
        sys.exit(f"refused: {e}")


if __name__ == "__main__":
    main()
