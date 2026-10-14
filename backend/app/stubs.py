"""Scripted model scenarios for stub mode (no network, no key). They prove plumbing and guard rails,
never model quality. In stub mode a model name is `stub:<scenario>`; drafter and verifier names must differ.

Drafter scenarios assume the synthetic Art 50(2) text used in tests and e2e (see SRC in tests).
"""
import json

OID = "obligations[OBL-ART50-2]"
SUP = [{"source_id": "S1", "locator": "placed on the market before 2 August 2026",
        "quote": "applies from 15 December 2026"}]
DATE_OP = {"op": "replace", "path": f"{OID}.effective.transition",
           "value": [{"if_placed_before": "2026-08-02", "effective": "2026-12-15"}],
           "support": SUP, "rationale": "Source gives a later date for systems already on the market"}
FABRICATED_OP = {**DATE_OP, "support": [{"source_id": "S1", "locator": "placed on the market before 2 August 2026",
                                         "quote": "applies from 1 January 2030"}]}

DRAFTERS = {"draft-supported": [DATE_OP], "draft-fabricated": [FABRICATED_OP], "draft-nochange": []}
VERIFIERS = {"verify-supported": "supported", "verify-contradicted": "contradicted", "verify-unverifiable": "unverifiable"}


def drafter(name):
    ops = DRAFTERS[name]

    def respond(_system, user):
        r = json.loads(user)
        return json.dumps({"base_revision": r["base_revision"], "source_hashes": r["source_hashes"],
                           "operations": ops, "unresolved": []})
    # one response per allowed attempt so a bad scenario exhausts repairs instead of the script
    return [respond] * 3


def verifier(name):
    verdict = VERIFIERS[name]

    def respond(_system, user):
        r = json.loads(user)
        fs = [{"operation_index": i, "field": o["path"], "verdict": verdict,
               "support": o["support"] if verdict == "supported" else [], "reason": f"stub {verdict}"}
              for i, o in enumerate(r["operations"])]
        return json.dumps({"patch_hash": r["patch_hash"], "findings": fs, "missing_context": []})
    return [respond] * 2
