import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { ErrorNote, Loading, Section } from "../components/ui";

export function RevisionsPage() {
  const q = useQuery({ queryKey: ["revisions"], queryFn: api.revisions });
  const [pair, setPair] = useState<{ from: string; to: string } | null>(null);
  const d = useQuery({ queryKey: ["diff", pair], queryFn: () => api.diff(pair!.from, pair!.to), enabled: !!pair });
  if (q.isPending) return <Loading what="revisions" />;
  if (q.isError) return <ErrorNote error={q.error} />;
  const revs = q.data;
  return (
    <>
      <h1>Revisions</h1>
      <table data-testid="revisions">
        <thead><tr><th>Revision (sha256)</th><th>Created</th><th>Receipt</th><th>Compare</th></tr></thead>
        <tbody>
          {revs.map((r, i) => (
            <tr key={r.sha256}>
              <td><code>{r.sha256.slice(0, 12)}</code>{i === 0 && " (current)"}</td>
              <td>{r.created_at ?? "baseline (not produced by a patch)"}</td>
              <td>{r.receipt_id ?? "none"}</td>
              <td>{i > 0 && <button onClick={() => setPair({ from: r.sha256, to: revs[0].sha256 })}>Diff to current</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {revs.length === 1 && <p className="muted">Only the baseline exists. Revisions appear here once a patch is committed.</p>}
      {pair && (
        <Section title="Changes">
          {d.isPending ? <Loading what="diff" /> : d.isError ? <ErrorNote error={d.error} /> : d.data.length === 0 ? <p>No differences.</p> :
            <ul>{d.data.map((e) => <li key={e.path}><code>{e.path}</code> ({e.op})</li>)}</ul>}
        </Section>
      )}
    </>
  );
}
