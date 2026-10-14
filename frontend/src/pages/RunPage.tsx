import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote, Loading, Section } from "../components/ui";

const MEANING: Record<string, string> = {
  running: "The drafter and verifier are working. This page refreshes by itself.",
  ready_for_review: "Every operation is backed by a quote the verifier confirmed. A named approver still has to decide; approval arrives in slice S3.",
  needs_revision: "At least one operation was contradicted or could not be verified. It cannot be approved as it stands.",
  escalated: "No valid patch was produced within the repair limit. A human should read the errors and the sources.",
  no_change: "The sources do not support any change to the register.",
  verifier_invalid: "The verifier's answer was unusable, so nothing was confirmed. Not approvable.",
  budget_exceeded: "The run stopped at its call or token cap. Not approvable.",
};
const VERDICT_MARK: Record<string, string> = { supported: "✔ supported", contradicted: "✖ contradicted", unverifiable: "? unverifiable" };
const json = (v: unknown) => JSON.stringify(v, null, 2);

export function RunPage() {
  const { id = "" } = useParams();
  const q = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.run(id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1000 : false),
  });
  if (q.isPending) return <Loading what={`run ${id}`} />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const r = q.data;
  const rv = r.review;
  return (
    <>
      <p><Link to="/runs">← Runs</Link></p>
      <h1>Run {r.id}</h1>
      <section className={`banner ${r.status === "ready_for_review" ? "calm" : ""}`} role="status" data-testid="run-status">
        <strong data-testid="status-text">{r.status.replaceAll("_", " ")}</strong>. {MEANING[r.status]}
      </section>
      <dl className="facts">
        <dt>Drafter</dt><dd>{r.drafter_model}</dd>
        <dt>Verifier</dt><dd>{r.verifier_model}</dd>
        <dt>Base revision</dt><dd><code>{r.base_revision.slice(0, 12)}</code></dd>
        {r.budget && <><dt>Budget used</dt><dd data-testid="budget">{r.budget.calls} of {r.budget.max_calls} calls · {r.budget.completion_tokens} of {r.budget.max_completion_tokens} completion tokens</dd></>}
        {rv?.patch_hash && <><dt>Patch hash</dt><dd><code data-testid="patch-hash">{rv.patch_hash}</code></dd></>}
      </dl>
      {rv && rv.flags.length > 0 && (
        <Section title="Flags (each must be acknowledged at approval)">
          <ul data-testid="flags">{rv.flags.map((f, i) => <li key={i}><strong>{f.flag}</strong>{f.op !== null && f.op !== undefined && ` · operation ${f.op}`} · {f.detail}</li>)}</ul>
        </Section>
      )}
      {rv && rv.errors.length > 0 && (
        <Section title="Errors"><ul data-testid="errors">{rv.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></Section>
      )}
      {rv && rv.ops.length > 0 && (
        <Section title="Proposed operations">
          {rv.ops.map((op, i) => (
            <article className="op" key={i} data-testid="op">
              <h3><code>{op.path}</code> <span className={`badge ${op.verdict === "supported" ? "ok" : "warn"}`}>{VERDICT_MARK[op.verdict]}</span></h3>
              <div className="diff">
                <div><h4>Current</h4><pre>{op.before === undefined ? "(not set)" : json(op.before)}</pre></div>
                <div><h4>Proposed</h4><pre>{json(op.value)}</pre></div>
              </div>
              {op.rationale && <p><em>Drafter:</em> {op.rationale}</p>}
              {op.verifier_note && <p><em>Verifier:</em> {op.verifier_note}</p>}
              {op.support.map((s, j) => (
                <blockquote key={j}>“{s.quote}”<footer>{s.source_id} · after “{s.locator}”</footer></blockquote>
              ))}
            </article>
          ))}
        </Section>
      )}
      {rv && (rv.unresolved?.length ?? 0) > 0 && <Section title="Unresolved (drafter)"><ul>{rv.unresolved!.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>}
      {rv && (rv.missing_context?.length ?? 0) > 0 && <Section title="Missing context (verifier)"><ul>{rv.missing_context!.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>}
      <p className="muted">Models propose and review. Verification status is unchanged; raising it to verified_primary is a separate human act.</p>
    </>
  );
}
