import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote, Loading } from "../components/ui";

export function RunsPage() {
  const q = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 3000 });
  if (q.isPending) return <Loading what="runs" />;
  if (q.isError) return <ErrorNote error={q.error} />;
  return (
    <>
      <h1>Runs</h1>
      {q.data.length === 0 ? <p className="muted">No runs yet. <Link to="/workflow">Propose a change</Link>.</p> : (
        <table data-testid="runs">
          <thead><tr><th>Run</th><th>Status</th><th>Drafter → verifier</th><th>Started</th></tr></thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.id}>
                <td><Link to={`/runs/${r.id}`}>{r.id}</Link></td>
                <td>{r.status.replaceAll("_", " ")}</td>
                <td>{r.drafter_model} → {r.verifier_model}</td>
                <td>{r.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
