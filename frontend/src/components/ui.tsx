import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiProblem } from "../api/client";

/** State is carried by text and shape, never colour alone. */
export function VerificationBadge({ status }: { status: string }) {
  const ok = status === "verified_primary";
  return <span className={`badge ${ok ? "ok" : "warn"}`}>{ok ? "✔ " : "⚠ "}{status.replace("_", " ")}</span>;
}

export function BlockedBanner({ blocked, total }: { blocked: number; total: number }) {
  if (blocked === 0) return null;
  return (
    <section className="banner" role="status" data-testid="blocked-banner">
      <strong>Blocked: {blocked} of {total} readings unverified.</strong> No automated compliance conclusion is shown
      until a named reviewer verifies the reading against the primary text.{" "}
      <Link to="/register">See which readings</Link>
    </section>
  );
}

export function Loading({ what }: { what: string }) {
  return <p aria-busy="true">Loading {what}…</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  const p = error instanceof ApiProblem ? error.problem : null;
  return (
    <p role="alert" className="error">
      {p ? `${p.title}${p.detail ? `: ${p.detail}` : ""} (${p.code})` : "Something went wrong."}
    </p>
  );
}

export function ProblemNote({ error }: { error: unknown }) {
  const p = error instanceof ApiProblem ? error.problem : null;
  if (!p) return <ErrorNote error={error} />;
  return (
    <div role="alert" className="error" data-testid="problem">
      <strong>{p.title}</strong> <code>{p.code}</code>
      {p.detail && <div>{p.detail}</div>}
      {p.violations && p.violations.length > 0 && <ul>{p.violations.map((v) => <li key={v}>{v}</li>)}</ul>}
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section><h2>{title}</h2>{children}</section>;
}
