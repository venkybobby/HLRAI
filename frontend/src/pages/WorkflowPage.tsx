import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Settings } from "../api/client";
import { ErrorNote, Loading, ProblemNote } from "../components/ui";

type Src = { source_id: string; text: string };
// Stub-mode scenario names are a dev/test aid; live names come from workflow_config.json.
const STUB_DRAFTERS = ["stub:draft-supported", "stub:draft-fabricated", "stub:draft-nochange"];
const STUB_VERIFIERS = ["stub:verify-supported", "stub:verify-contradicted", "stub:verify-unverifiable"];

export function WorkflowPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  if (settings.isPending) return <Loading what="settings" />;
  if (settings.isError) return <ErrorNote error={settings.error} />;
  return <Form s={settings.data} />;
}

function Form({ s }: { s: Settings }) {
  const nav = useNavigate();
  const stub = s.model_mode === "stub";
  const [sources, setSources] = useState<Src[]>([{ source_id: "S1", text: "" }]);
  const [drafter, setDrafter] = useState(stub ? STUB_DRAFTERS[0] : s.default_drafter ?? "");
  const [verifier, setVerifier] = useState(stub ? STUB_VERIFIERS[0] : s.default_verifier ?? "");
  const chars = sources.reduce((n, x) => n + x.text.length, 0);
  const over = chars > s.limits.max_packet_chars;

  const start = useMutation({
    mutationFn: async () => {
      const packet = await api.createPacket({ obligation_id: s.scope_obligation, sources });
      return api.startRun({ packet_id: packet.id, drafter_model: drafter, verifier_model: verifier, allow_same_model: false });
    },
    onSuccess: (run) => nav(`/runs/${run.id}`),
  });

  const setSrc = (i: number, patch: Partial<Src>) => setSources((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  return (
    <>
      <h1>Propose a change</h1>
      <p className="muted">
        A drafter model proposes narrowly scoped edits to <strong>{s.scope_obligation}</strong> from the sources you paste;
        a different verifier model checks each edit against the quoted text. Nothing is written to the register by this
        page. Sources are treated as evidence, never as instructions.
      </p>
      {stub && <p className="banner" role="status" data-testid="stub-mode">Stub mode: scripted models, no network. Results prove plumbing, not model quality.</p>}
      <form onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
        <fieldset>
          <legend>Sources</legend>
          {sources.map((x, i) => (
            <div className="src" key={i}>
              <label>Source ID
                <input value={x.source_id} onChange={(e) => setSrc(i, { source_id: e.target.value })} required />
              </label>
              <label>Text (paste the primary text)
                <textarea rows={6} value={x.text} onChange={(e) => setSrc(i, { text: e.target.value })} required />
              </label>
              {sources.length > 1 && <button type="button" onClick={() => setSources((xs) => xs.filter((_, j) => j !== i))}>Remove source</button>}
            </div>
          ))}
          <button type="button" onClick={() => setSources((xs) => [...xs, { source_id: `S${xs.length + 1}`, text: "" }])}>Add source</button>
          <p className={over ? "error" : "muted"} data-testid="char-count">
            {chars.toLocaleString()} of {s.limits.max_packet_chars.toLocaleString()} characters{over && " — over the limit; no model call will be made"}
          </p>
        </fieldset>
        <fieldset>
          <legend>Models</legend>
          <label>Drafter
            <input list="drafters" value={drafter} onChange={(e) => setDrafter(e.target.value)} required />
          </label>
          <label>Verifier (must differ from the drafter)
            <input list="verifiers" value={verifier} onChange={(e) => setVerifier(e.target.value)} required />
          </label>
          {stub && <><datalist id="drafters">{STUB_DRAFTERS.map((n) => <option key={n} value={n} />)}</datalist>
            <datalist id="verifiers">{STUB_VERIFIERS.map((n) => <option key={n} value={n} />)}</datalist></>}
          <p className="muted">Limits per run: {s.limits.max_calls} calls, {s.limits.max_tokens_per_call} tokens per call, {s.limits.max_total_completion_tokens} completion tokens, up to {s.limits.max_repairs} repairs.</p>
        </fieldset>
        <button type="submit" disabled={start.isPending || over || chars === 0}>{start.isPending ? "Starting…" : "Start run"}</button>
      </form>
      {start.isError && <ProblemNote error={start.error} />}
    </>
  );
}
