import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote, Loading, Section, VerificationBadge } from "../components/ui";

export function ObligationPage() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["obligation", id], queryFn: () => api.obligation(id) });
  if (q.isPending) return <Loading what={id} />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const { obligation: o, controls, evaluation_ids, blocked_reason } = q.data;
  return (
    <>
      <p><Link to="/register">← Register</Link></p>
      <h1>{o.id}</h1>
      {blocked_reason && <section className="banner" role="status" data-testid="blocked-reason">{blocked_reason}</section>}
      <dl className="facts">
        <dt>Legal source</dt><dd>{o.legal_source.instrument}, Art {o.legal_source.article} ({o.legal_source.status})</dd>
        <dt>Actor</dt><dd>{o.actor}</dd>
        <dt>Trigger</dt><dd>{o.trigger}</dd>
        <dt>Duty</dt><dd>{o.duty}</dd>
        <dt>Effective</dt>
        <dd>{o.effective.default}{o.effective.transition.map((t, i) => <div key={i}>transition: if placed before {t.if_placed_before} → {t.effective}</div>)}</dd>
        <dt>Reading</dt><dd><VerificationBadge status={o.verification.status} /></dd>
      </dl>
      <Section title="Verification">
        <p>{o.verification.source_version}</p>
        <p>Reviewer: {o.verification.reviewer ?? "none"} · Verified at: {o.verification.verified_at ?? "never"}</p>
        <ul>{o.verification.sources.map((s) => <li key={s}>{s}</li>)}</ul>
      </Section>
      <Section title="Exceptions">
        {o.exceptions.length === 0 ? <p className="muted">None recorded.</p> : <ul>{o.exceptions.map((e) => <li key={e.id}>{e.id}: {e.text}</li>)}</ul>}
      </Section>
      <Section title="Controls">
        <ul>{controls.map((c) => <li key={c.id}>{c.id} · category {c.category}
          <ul>{c.requirements.map((r) => <li key={r.id}>{r.id} <span className="muted">[{r.legal_status}]</span> {r.text}</li>)}</ul></li>)}</ul>
      </Section>
      <Section title="Evaluations">
        <p>{evaluation_ids.length ? evaluation_ids.join(", ") : "None."}</p>
      </Section>
    </>
  );
}
