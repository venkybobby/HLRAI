"""File-backed register (spec section 4: the YAML file in git stays canonical).

Everything the API shows is derived from the register bytes. Rules (derive, schema
checks, diffing paths) are imported from the root modules, never re-implemented.
"""
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "workflow"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import check_register as cr  # noqa: E402
import pipeline as wf  # noqa: E402

REGISTER = "eu-ai-act-register.yaml"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_plain(b: bytes) -> dict:
    return yaml.load(b.decode(), Loader=cr.Loader)


class RegisterStore:
    def __init__(self, root=None, state=None):
        self.root = Path(root) if root else ROOT
        self.state = Path(state) if state else self.root / ".workflow-state"

    @property
    def path(self) -> Path:
        return self.root / REGISTER

    def raw(self) -> bytes:
        return self.path.read_bytes()

    def revision(self) -> str:
        return sha(self.raw())

    def doc(self) -> dict:
        return load_plain(self.raw())

    def revision_bytes(self, rev: str):
        if rev == self.revision():
            return self.raw()
        f = self.state / "history" / f"{rev}.yaml"
        return f.read_bytes() if f.exists() else None

    def receipts(self) -> list:
        d = self.state / "receipts"
        return [json.loads(f.read_text()) for f in sorted(d.glob("*.json"))] if d.exists() else []

    def revisions(self) -> list:
        """Newest first. created_at is known only for revisions produced by a committed patch."""
        made = {r["revision_after"]: r for r in self.receipts()}
        known = {self.revision(), *made}
        hist = self.state / "history"
        if hist.exists():
            known |= {f.stem for f in hist.glob("*.yaml")}
        cur = self.revision()
        rows = [{"sha256": s, "created_at": made[s]["committed_at"] if s in made else None,
                 "receipt_id": made[s]["patch_hash"] if s in made else None} for s in known]
        rows.sort(key=lambda r: (r["sha256"] != cur, r["created_at"] is None, _neg(r["created_at"])))
        return rows


def _neg(ts):
    return "" if ts is None else "".join(chr(0x10FFFF - ord(c)) for c in ts)


def value_at(doc, path):
    """(found, value) for a pipeline path, including whole-record paths like obligations[ID]."""
    try:
        parent, key = wf.resolve_parent(doc, path)
        return True, parent[key]
    except (KeyError, ValueError):
        pass
    segs = wf.parse_path(path)
    name, ident = segs[-1]
    if ident is not None and len(segs) == 1:
        for x in doc.get(name, []):
            if isinstance(x, dict) and x.get("id") == ident:
                return True, x
    return False, None
