"""Read-side use cases for slice S1. No writes. Rules come from check_register / pipeline."""
from .errors import ApiError
from .register_store import RegisterStore, cr, load_plain, value_at, wf


def _blocked_reason(obl, policy):
    need = policy["min_verification_for_automated_conclusion"]
    have = obl["verification"]["status"]
    if have == need:
        return None
    return f"Reading of {obl['id']} is {have}; automated conclusions require {need} with a named reviewer."


def _outcome(o):
    return {"completion": o["completion"], "operating_permission": o["operating_permission"], "flags": o["flags"]}


def _eval_view(ev, obls, ctls, policy):
    obl, ctl = obls[ev["obligation"]], ctls[ev["control"]]
    return {"evaluation": ev,
            "now": _outcome(cr.derive(ev, obl, ctl, policy)),
            "if_verified": _outcome(cr.derive(ev, obl, ctl, policy, assume_verified=True))}


def summary(store: RegisterStore):
    doc = store.doc()
    policy = doc["conclusion_policy"]
    obls = {o["id"]: o for o in doc["obligations"]}
    ctls = {c["id"]: c for c in doc["controls"]}
    index = doc["migration"]["register_index"]
    return {
        "revision": store.revision(),
        "status": doc["status"],
        "conclusion_policy": policy,
        "obligations": [{"id": o["id"], "actor": o["actor"], "duty": o["duty"],
                         "verification_status": o["verification"]["status"],
                         "blocked": _blocked_reason(o, policy) is not None} for o in doc["obligations"]],
        "controls": [{"id": c["id"], "category": c["category"], "criticality": c["criticality"]} for c in doc["controls"]],
        "evaluations": [_eval_view(e, obls, ctls, policy) for e in doc["evaluations"]],
        "migration": {"migrated": sum(1 for r in index if r.get("ctl")), "total": len(index)},
    }


def obligation_detail(store: RegisterStore, oid: str):
    doc = store.doc()
    obl = next((o for o in doc["obligations"] if o["id"] == oid), None)
    if not obl:
        raise ApiError(404, "not_found", "Obligation not found", f"No obligation {oid}")
    ctls = {c["id"]: c for c in doc["controls"]}
    return {"obligation": obl, "controls": [ctls[c] for c in obl["controls"]],
            "evaluation_ids": [e["id"] for e in doc["evaluations"] if e["obligation"] == oid],
            "blocked_reason": _blocked_reason(obl, doc["conclusion_policy"])}


def control_detail(store: RegisterStore, cid: str):
    c = next((c for c in store.doc()["controls"] if c["id"] == cid), None)
    if not c:
        raise ApiError(404, "not_found", "Control not found", f"No control {cid}")
    return c


def diff(store: RegisterStore, a: str, b: str):
    ba, bb = store.revision_bytes(a), store.revision_bytes(b)
    for rev, got in ((a, ba), (b, bb)):
        if got is None:
            raise ApiError(404, "not_found", "Revision not found", f"No stored copy of revision {rev}")
    da, db = load_plain(ba), load_plain(bb)
    out = []
    for path in wf.diff_paths(da, db):
        fa, va = value_at(da, path)
        fb, vb = value_at(db, path)
        entry = {"path": path, "op": "changed" if fa and fb else "added" if fb else "removed"}
        if fa:
            entry["before"] = va
        if fb:
            entry["after"] = vb
        out.append(entry)
    return out
