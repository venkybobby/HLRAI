#!/usr/bin/env python3
"""Validate and test the EU AI Act register records (pilot v0.2).

Layers:
  1. JSON Schema contract (fields, types, enums, conditional constraints)
  2. Referential integrity and cross-field arithmetic
  3. Derivation: outcome computed from inputs, compared with `recorded` and `expected`
  4. Forbidden-state assertions, proven live by negative fixtures
  5. Coverage and migration status generated from the register index

Usage: python3 check_register.py   (exit code 1 on any failure)
"""
import copy
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
COMPLETE = {"satisfied", "conditionally_satisfied", "closed_late"}
# Totals from the register document's coverage table, independently recounted in review.
DOC_TOTALS = {"rows": 69, "A": 14, "B": 12, "A+C": 34, "C": 9}


class Loader(yaml.SafeLoader):
    pass


# Keep dates and timestamps as strings; the schema and checker parse them explicitly.
Loader.add_constructor("tag:yaml.org,2002:timestamp", lambda l, n: l.construct_scalar(n))

D = date.fromisoformat
T = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))


def end_of(d):
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


# ---------------------------------------------------------------- derivation
def effective_date(obl, system):
    due = D(obl["effective"]["default"])
    pob = system.get("placed_on_market")
    for t in obl["effective"]["transition"]:
        if pob and D(pob) < D(t["if_placed_before"]):
            due = max(due, D(t["effective"]))
    return due


def computed_applicability(ev, obl):
    asof, default, due = D(ev["as_of"]), D(obl["effective"]["default"]), effective_date(obl, ev["system"])
    if asof < default:
        return "not_yet_effective"
    return "in_transition" if asof < due else "applicable"


def derive(ev, obl, ctl, policy, assume_verified=False):
    """Pure function: outcome from inputs. Never reads `recorded` or `expected`."""
    flags, asof = set(), D(ev["as_of"])
    inc = ev.get("incident")
    if inc and T(inc["ticket_created_at"]) > T(inc["awareness_at"]):
        flags.add("ticket_created_after_awareness")

    def out(completion, permission):
        return {"completion": completion, "operating_permission": permission, "flags": sorted(flags)}

    if not assume_verified and obl["verification"]["status"] != policy["min_verification_for_automated_conclusion"]:
        flags.add("unverified_interpretation")
        return out("blocked_unverified_interpretation", "undetermined")

    app = ev["applicability"]
    if app["value"] == "unresolved":
        flags.add("applicability_unresolved")
        return out("open", "undetermined")
    if app["value"] == "not_yet_effective":
        return out("not_yet_effective", "permitted")
    if app["value"] == "not_applicable":
        complete = all(app.get(k) for k in ("approved_by", "reasoning", "expires", "reassess_on"))
        if not complete or D(app["expires"]) <= asof:
            flags.add("exemption_invalid_or_expired")
            return out("open", "undetermined")
        if set(ev.get("events_since_approval", [])) & set(app["reassess_on"]):
            flags.add("exemption_reassessment_triggered")
            return out("open", "undetermined")
        return out("not_applicable_approved", "permitted")

    evidence, result = ev["evidence_validity"]["value"], ev["control_result"]["value"]
    failing = False
    if evidence != "valid":
        flags.add(f"evidence_{evidence}")
        failing = True
    if result != "pass":
        flags.add({"fail": "control_failed", "inconclusive": "control_inconclusive", "execution_error": "control_execution_error"}[result])
        failing = True
    if failing:
        if app["value"] == "in_transition" and asof < effective_date(obl, ev["system"]):
            flags.add("before_due_date")
            return out("open", policy["pre_due_date_failure_permission"])
        return out("open", ctl["on_fail"]["permission"])

    completion, permission = "satisfied", "permitted"
    if ctl["category"] in ("A+C", "C"):
        a = ev["assurance"]
        if a["value"] == "accepted_with_restrictions":
            if D(a["expires"]) <= asof:
                flags.add("restrictions_expired")
                return out("open", "not_permitted")
            completion, permission = "conditionally_satisfied", "permitted_with_restrictions"
        elif a["value"] == "rejected":
            flags.add("assurance_rejected")
            return out("open", ctl["on_fail"]["permission"])
        elif a["value"] != "accepted":
            flags.add("awaiting_assurance")
            return out("open", "undetermined")

    if inc:
        deadline, sub = T(inc["deadline_at"]), inc.get("submission")
        if sub and T(sub["submitted_at"]) > deadline:
            flags.add("deadline_missed")  # lateness is permanent; remediation never clears it
            completion = "closed_late"
        elif not sub and end_of(asof) > deadline:
            flags.add("deadline_missed")
            return out("open", ctl["on_fail"]["permission"])
        elif not sub:
            flags.add("awaiting_submission")
            return out("open", "permitted")
    return out(completion, permission)


# ------------------------------------------------------ forbidden states
def forbidden(ev, obl, ctl, policy):
    """Rules applied to the RECORDED outcome, independent of derive()."""
    v, rec, asof = [], ev["recorded"], D(ev["as_of"])
    comp, perm = rec["completion"], rec["operating_permission"]
    app = ev["applicability"]["value"]
    evidence = ev.get("evidence_validity", {}).get("value")
    result = ev.get("control_result", {}).get("value")
    assurance = ev.get("assurance", {})
    done = comp in COMPLETE
    if done and evidence != "valid":
        v.append("F1 completion recorded without valid evidence")
    if app == "unresolved" and (done or comp == "not_applicable_approved"):
        v.append("F2 completion recorded while applicability is unresolved")
    if perm == "permitted_with_restrictions" and (not assurance.get("expires") or D(assurance["expires"]) <= asof):
        v.append("F3 operating permission relies on expired or missing restrictions")
    if comp == "satisfied" and assurance.get("value") == "accepted_with_restrictions":
        v.append("F4 restricted acceptance recorded as fully satisfied")
    if comp == "conditionally_satisfied" and assurance.get("value") != "accepted_with_restrictions":
        v.append("F4b conditional completion without restricted acceptance")
    inc = ev.get("incident")
    if inc:
        sub, late = inc.get("submission"), False
        if sub and T(sub["submitted_at"]) > T(inc["deadline_at"]):
            late = True
        elif not sub and end_of(asof) > T(inc["deadline_at"]) and app in ("applicable", "in_transition"):
            late = True
        if late and not inc["deadline_missed"]:
            v.append("F5 historical deadline failure not preserved")
        if late and comp == "satisfied":
            v.append("F5b late report recorded as satisfied")
        if not late and inc["deadline_missed"]:
            v.append("F5c deadline_missed set without a late submission")
    if comp == "not_applicable_approved":
        a = ev["applicability"]
        if app != "not_applicable" or not all(a.get(k) for k in ("approved_by", "reasoning", "expires", "reassess_on")):
            v.append("F6 exemption recorded without approved reasoning")
    if done and result != "pass":
        v.append("F7 completion recorded while the control did not pass")
    if obl["verification"]["status"] != policy["min_verification_for_automated_conclusion"] and comp != "blocked_unverified_interpretation":
        v.append("F8 conclusion recorded on an unverified interpretation")
    if ctl["category"] in ("A+C", "C") and done and assurance.get("value") not in ("accepted", "accepted_with_restrictions"):
        v.append("F9 completion recorded without human assurance")
    return v


def pass_rate(outcomes):
    """Exemptions, not-yet-effective rows and unresolved/blocked rows leave the denominator."""
    excluded = {"not_applicable_approved", "not_yet_effective", "blocked_unverified_interpretation"}
    den = [o for o in outcomes if o["completion"] not in excluded and "applicability_unresolved" not in o["flags"]]
    num = [o for o in den if o["completion"] == "satisfied"]
    return len(num), len(den)


def incident_arithmetic_ok(ev, obl):
    inc = ev.get("incident")
    if not inc:
        return True
    days = obl["periods_days"][inc["class"]]
    return T(inc["deadline_at"]) == T(inc["awareness_at"]) + timedelta(days=days)


# ------------------------------------------------------------------ harness
class Results:
    def __init__(self):
        self.rows = []

    def check(self, name, cond, detail=""):
        self.rows.append((bool(cond), name, "" if cond else detail))

    @property
    def failed(self):
        return [r for r in self.rows if not r[0]]


def main(register_path=None, write_report=True):
    R = Results()
    doc = yaml.load(Path(register_path or HERE / "eu-ai-act-register.yaml").read_text(), Loader=Loader)
    schema = __import__("json").loads((HERE / "eu-ai-act-register.schema.json").read_text())
    validator = Draft202012Validator(schema)
    Draft202012Validator.check_schema(schema)

    # 1. contract
    errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    R.check("schema: records satisfy the JSON Schema contract", not errs,
            "; ".join(f"{'/'.join(map(str, e.path))}: {e.message[:90]}" for e in errs[:5]))
    obls = {o["id"]: o for o in doc["obligations"]}
    ctls = {c["id"]: c for c in doc["controls"]}
    evals = {e["id"]: e for e in doc["evaluations"]}
    policy = doc["conclusion_policy"]

    # 2. integrity
    for o in doc["obligations"]:
        for c in o["controls"]:
            R.check(f"integrity: {o['id']} -> {c} exists and implements it",
                    c in ctls and o["id"] in ctls[c]["implements"])
    for c in doc["controls"]:
        for o in c["implements"]:
            R.check(f"integrity: {c['id']} implements {o}, which lists it back", o in obls and c["id"] in obls[o]["controls"])
    for e in doc["evaluations"]:
        R.check(f"integrity: {e['id']} references a control that implements its obligation",
                e["obligation"] in obls and e["control"] in ctls and e["obligation"] in ctls[e["control"]]["implements"])
    for c in doc["controls"]:
        R.check(f"legal status: {c['id']} labels every requirement individually",
                all(r["legal_status"] for r in c["requirements"]))
    mixed = [c["id"] for c in doc["controls"] if len({r["legal_status"] for r in c["requirements"]}) > 1]
    R.check("legal status: mixed-basis controls keep distinct requirement labels", len(mixed) >= 1, "no mixed control found")
    idx = doc["migration"]["register_index"]
    R.check("migration: row ids unique", len({r["row"] for r in idx}) == len(idx))
    for r in idx:
        if r["ctl"]:
            R.check(f"migration: {r['row']} category matches {r['ctl']}", r["ctl"] in ctls and ctls[r["ctl"]]["category"] == r["cat"])
    cnt = Counter(r["cat"] for r in idx)
    got = {"rows": len(idx), "A": cnt["A"], "B": cnt["B"], "A+C": cnt["A+C"], "C": cnt["C"]}
    R.check("migration: index totals equal the document coverage table", got == DOC_TOTALS, f"{got} != {DOC_TOTALS}")

    # applicability and arithmetic on stored data
    for e in doc["evaluations"]:
        o, c = obls[e["obligation"]], ctls[e["control"]]
        rec = e["applicability"]["value"]
        if rec in ("applicable", "in_transition", "not_yet_effective"):
            R.check(f"applicability: {e['id']} recorded '{rec}' matches the dates", rec == computed_applicability(e, o),
                    f"computed {computed_applicability(e, o)}")
        R.check(f"incident arithmetic: {e['id']} deadline is awareness plus the Art 73 period", incident_arithmetic_ok(e, o))

    # 3. derivation vs recorded vs expected (the pilot evaluations)
    for e in doc["evaluations"]:
        o, c = obls[e["obligation"]], ctls[e["control"]]
        now, ver = derive(e, o, c, policy), derive(e, o, c, policy, assume_verified=True)
        R.check(f"{e['id']} now: derived == expected", now == {**e["expected"]["now"], "flags": sorted(e["expected"]["now"].get("flags", []))}, f"{now}")
        R.check(f"{e['id']} if verified: derived == expected", ver == {**e["expected"]["if_verified"], "flags": sorted(e["expected"]["if_verified"].get("flags", []))}, f"{ver}")
        R.check(f"{e['id']} recorded outcome equals derived outcome (no drift)",
                e["recorded"]["completion"] == now["completion"] and e["recorded"]["operating_permission"] == now["operating_permission"])
        R.check(f"{e['id']} forbidden states absent in stored data", not forbidden(e, o, c, policy), "; ".join(forbidden(e, o, c, policy)))
    R.check("gate: every stored evaluation is blocked while no reading is verified_primary",
            all(derive(e, obls[e["obligation"]], ctls[e["control"]], policy)["completion"] == "blocked_unverified_interpretation" for e in doc["evaluations"]))

    # 4. negative fixtures: each forbidden state must be caught
    def fx(base, **kw):
        e = copy.deepcopy(evals[base])
        for k, v in kw.items():
            e[k] = v
        return e

    def codes(e):
        return {x.split()[0] for x in forbidden(e, obls[e["obligation"]], ctls[e["control"]], policy)}

    def der(e, verified=True):
        return derive(e, obls[e["obligation"]], ctls[e["control"]], policy, assume_verified=verified)

    done = {"completion": "satisfied", "operating_permission": "permitted"}
    R.check("F1: missing evidence + completion is rejected", "F1" in codes(fx("EVAL-0002", recorded=done)))
    R.check("F2: unresolved applicability + completion is rejected",
            "F2" in codes(fx("EVAL-0001", applicability={"value": "unresolved", "reasoning": "scope unclear"}, recorded=done)))
    expired = fx("EVAL-0001", evidence_validity={"value": "valid"}, control_result={"value": "pass"},
                 assurance={"value": "accepted_with_restrictions", "restrictions": ["EU users only"], "expires": "2026-09-01"},
                 recorded={"completion": "conditionally_satisfied", "operating_permission": "permitted_with_restrictions"})
    R.check("F3: expired restrictions + operating permission is rejected", "F3" in codes(expired))
    d = der(expired)
    R.check("F3: derivation withdraws permission when restrictions expire",
            d["completion"] == "open" and d["operating_permission"] == "not_permitted" and "restrictions_expired" in d["flags"], str(d))
    restricted = fx("EVAL-0001", evidence_validity={"value": "valid"}, control_result={"value": "pass"},
                    assurance={"value": "accepted_with_restrictions", "restrictions": ["EU users only"], "expires": "2027-01-01"}, recorded=done)
    R.check("F4: restricted acceptance recorded as satisfied is rejected", "F4" in codes(restricted))
    d = der(restricted)
    R.check("F4: derivation gives conditionally_satisfied, never satisfied",
            d["completion"] == "conditionally_satisfied" and d["operating_permission"] == "permitted_with_restrictions", str(d))
    R.check("F7: control failure + completion is rejected", "F7" in codes(fx("EVAL-0001", recorded=done)))
    R.check("F8: conclusion on an unverified reading is rejected",
            "F8" in codes(fx("EVAL-0001", recorded={"completion": "open", "operating_permission": "permitted"})))
    R.check("F9: A+C completion without human assurance is rejected",
            "F9" in codes(fx("EVAL-0001", evidence_validity={"value": "valid"}, control_result={"value": "pass"}, recorded=done)))

    late = fx("EVAL-0004", as_of="2028-01-20", applicability={"value": "applicable", "reasoning": "Annex III high-risk in force", "approved_by": "legal_counsel"},
              assurance={"value": "accepted"},
              incident={"class": "general", "awareness_at": "2028-01-02T10:00:00Z", "ticket_created_at": "2028-01-02T12:00:00Z",
                        "deadline_at": "2028-01-17T10:00:00Z", "deadline_missed": True,
                        "submission": {"submitted_at": "2028-01-19T09:00:00Z", "receipt_ref": "ref://receipt/demo"},
                        "remediation": {"opened_at": "2028-01-19", "completed_at": "2028-01-20"}},
              recorded={"completion": "closed_late", "operating_permission": "permitted"})
    R.check("incident: arithmetic holds for the late fixture", incident_arithmetic_ok(late, obls["OBL-ART73"]))
    d = der(late)
    R.check("incident: late submission derives closed_late with deadline_missed, even after remediation completes",
            d["completion"] == "closed_late" and "deadline_missed" in d["flags"], str(d))
    verified_obl = copy.deepcopy(obls["OBL-ART73"])
    verified_obl["verification"].update(status="verified_primary", reviewer="test-reviewer", verified_at="2026-10-04")
    R.check("incident: faithfully recorded late report has no forbidden state once the reading is verified",
            not forbidden(late, verified_obl, ctls["CTL-INCIDENT-CLOCK"], policy), str(forbidden(late, verified_obl, ctls["CTL-INCIDENT-CLOCK"], policy)))
    cleared = copy.deepcopy(late)
    cleared["incident"]["deadline_missed"] = False
    R.check("F5: clearing the lateness flag after remediation is rejected", "F5" in codes(cleared))
    relabeled = copy.deepcopy(late)
    relabeled["recorded"]["completion"] = "satisfied"
    R.check("F5b: relabelling a late report as satisfied is rejected", "F5b" in codes(relabeled))
    tampered = copy.deepcopy(late)
    tampered["incident"]["deadline_at"] = "2028-01-20T10:00:00Z"
    R.check("incident: deadline measured from ticket creation instead of awareness is detected",
            not incident_arithmetic_ok(tampered, obls["OBL-ART73"]))

    bad = fx("EVAL-0003", events_since_approval=["compute_threshold_change"])
    d = der(bad)
    R.check("exemption: a relevant change forces reassessment (open, not satisfied)",
            d["completion"] == "open" and "exemption_reassessment_triggered" in d["flags"], str(d))
    lapsed = copy.deepcopy(evals["EVAL-0003"])
    lapsed["applicability"]["expires"] = "2026-10-03"
    d = der(lapsed)
    R.check("exemption: an expired approval reopens the row", d["completion"] == "open" and "exemption_invalid_or_expired" in d["flags"], str(d))
    broken = copy.deepcopy(doc)
    del broken["evaluations"][2]["applicability"]["approved_by"]
    R.check("F6 (contract): exemption without an approver fails schema validation", any(True for _ in validator.iter_errors(broken)))
    broken = copy.deepcopy(doc)
    broken["obligations"][0]["verification"]["status"] = "verified_primary"
    R.check("contract: verified_primary without a named reviewer fails schema validation", any(True for _ in validator.iter_errors(broken)))
    broken = copy.deepcopy(doc)
    broken["controls"][1].pop("threshold")
    R.check("contract: a B control without a pre-approved threshold fails schema validation", any(True for _ in validator.iter_errors(broken)))
    broken = copy.deepcopy(doc)
    broken["retention_schedule"][3]["period"]["value"] = 5
    R.check("contract: a retention period with no legal decision is rejected", any(True for _ in validator.iter_errors(broken)))

    outage = fx("EVAL-0001", control_result={"value": "execution_error", "detail": "scanner unavailable"})
    d = der(outage)
    R.check("outage: an unavailable integration is an execution error, never not_applicable",
            d["completion"] == "open" and "control_execution_error" in d["flags"], str(d))
    R.check("pass rate: approved exemptions leave the denominator and never count as satisfied",
            pass_rate([{"completion": "satisfied", "flags": []}, {"completion": "not_applicable_approved", "flags": []}]) == (1, 1))
    R.check("pass rate: a late report counts in the denominator but not as satisfied",
            pass_rate([{"completion": "closed_late", "flags": ["deadline_missed"]}, {"completion": "satisfied", "flags": []}]) == (1, 2))

    # 5. coverage and migration report (generated, never hand-edited)
    by_reg = defaultdict(Counter)
    unmigrated = defaultdict(list)
    for r in idx:
        by_reg[r["reg"]][r["cat"]] += 1
        by_reg[r["reg"]]["rows"] += 1
        if r["ctl"]:
            by_reg[r["reg"]]["migrated"] += 1
        else:
            unmigrated[r["reg"]].append(r["row"])
    migrated = sum(1 for r in idx if r["ctl"])
    lines = ["# Migration status (generated by check_register.py; do not edit)", "",
             f"{migrated} of {len(idx)} register rows are migrated to structured records; {len(idx) - migrated} are not.", "",
             "| Register | Rows | A | B | A+C | C | Migrated |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for reg, c in by_reg.items():
        lines.append(f"| {reg} | {c['rows']} | {c['A']} | {c['B']} | {c['A+C']} | {c['C']} | {c['migrated']} |")
    lines.append(f"| **Total** | **{len(idx)}** | **{cnt['A']}** | **{cnt['B']}** | **{cnt['A+C']}** | **{cnt['C']}** | **{migrated}** |")
    lines += ["", "## Not yet migrated", ""] + [f"- {reg}: {', '.join(rows)}" for reg, rows in unmigrated.items()]
    lines += ["", "## Pilot evaluation outcomes", "", "| Evaluation | Now | If every reading were verified |", "| --- | --- | --- |"]
    for e in doc["evaluations"]:
        o, c = obls[e["obligation"]], ctls[e["control"]]
        n, v = derive(e, o, c, policy), derive(e, o, c, policy, assume_verified=True)
        lines.append(f"| {e['id']} {e['scenario']} | {n['completion']} / {n['operating_permission']} | {v['completion']} / {v['operating_permission']} |")
    if write_report:
        (HERE / "migration-status.md").write_text("\n".join(lines) + "\n")

    # report
    for ok, name, detail in R.rows:
        print(("PASS " if ok else "FAIL ") + name + (f"\n     -> {detail}" if detail else ""))
    print(f"\n{len(R.rows) - len(R.failed)} passed, {len(R.failed)} failed, {len(R.rows)} checks")
    return 1 if R.failed else 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--register", help="check this register file instead of the default")
    ap.add_argument("--no-report", action="store_true", help="do not rewrite migration-status.md")
    args = ap.parse_args()
    sys.exit(main(args.register, write_report=not args.no_report))
