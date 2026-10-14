import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { BlockedBanner, ErrorNote, Loading, Section, VerificationBadge } from "../components/ui";

export function RegisterPage() {
  const q = useQuery({ queryKey: ["register"], queryFn: api.register });
  if (q.isPending) return <Loading what="register" />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const r = q.data;
  return (
    <>
      <h1>Register</h1>
      <BlockedBanner blocked={r.obligations.filter((o) => o.blocked).length} total={r.obligations.length} />
      <Section title="Obligations">
        <table data-testid="obligations">
          <thead><tr><th>ID</th><th>Actor</th><th>Duty</th><th>Reading</th></tr></thead>
          <tbody>
            {r.obligations.map((o) => (
              <tr key={o.id}>
                <td><Link to={`/obligations/${o.id}`}>{o.id}</Link></td>
                <td>{o.actor}</td>
                <td>{o.duty}</td>
                <td><VerificationBadge status={o.verification_status} />{o.blocked && <span className="sr"> blocked</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Controls">
        <ul>{r.controls.map((c) => <li key={c.id}>{c.id} · category {c.category} · {c.criticality}</li>)}</ul>
      </Section>
      <Section title="Evaluations (pilot data)">
        <table data-testid="evaluations">
          <thead><tr><th>ID</th><th>Scenario</th><th>Now</th><th>If every reading were verified</th></tr></thead>
          <tbody>
            {r.evaluations.map((e) => (
              <tr key={e.evaluation.id}>
                <td>{e.evaluation.id}</td>
                <td>{e.evaluation.scenario}</td>
                <td>{e.now.completion} / {e.now.operating_permission}</td>
                <td className="muted">{e.if_verified.completion} / {e.if_verified.operating_permission}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </>
  );
}
