import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { ObligationPage } from "./pages/ObligationPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RegisterPage } from "./pages/RegisterPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { RevisionsPage } from "./pages/RevisionsPage";

export function App() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <strong>HLRAI</strong>
        <nav aria-label="Primary">
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/register">Register</NavLink>
          <NavLink to="/workflow">Propose</NavLink>
          <NavLink to="/runs">Runs</NavLink>
          <NavLink to="/revisions">Revisions</NavLink>
        </nav>
        <span className="who" data-testid="who">{me.data ? `${me.data.name} (${me.data.role})` : "…"}</span>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/obligations/:id" element={<ObligationPage />} />
          <Route path="/workflow" element={<WorkflowPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="/revisions" element={<RevisionsPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
      <footer>
        Not legal advice. Readings are unverified against the Official Journal unless marked verified_primary.
        Pilot data is fictional.
      </footer>
    </>
  );
}
