import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { BlockedBanner, ErrorNote, Loading } from "../components/ui";

export function OverviewPage() {
  const q = useQuery({ queryKey: ["register"], queryFn: api.register });
  if (q.isPending) return <Loading what="register" />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const r = q.data;
  const blocked = r.obligations.filter((o) => o.blocked).length;
  return (
    <>
      <h1>Overview</h1>
      <BlockedBanner blocked={blocked} total={r.obligations.length} />
      <dl className="stats">
        <div><dt>Obligations</dt><dd data-testid="stat-obligations">{r.obligations.length}</dd></div>
        <div><dt>Controls</dt><dd>{r.controls.length}</dd></div>
        <div><dt>Evaluations</dt><dd>{r.evaluations.length}</dd></div>
        <div><dt>Rows migrated</dt><dd data-testid="stat-migrated">{r.migration.migrated} of {r.migration.total}</dd></div>
      </dl>
      <p className="muted">Register status: {r.status} · revision <code>{r.revision.slice(0, 12)}</code></p>
    </>
  );
}
