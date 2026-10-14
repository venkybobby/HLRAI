import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Problem = components["schemas"]["Problem"];
export type RegisterSummary = components["schemas"]["RegisterSummary"];
export type ObligationDetail = components["schemas"]["ObligationDetail"];
export type EvaluationView = components["schemas"]["EvaluationView"];
export type Revision = components["schemas"]["Revision"];
export type DiffEntry = components["schemas"]["DiffEntry"];
export type Settings = components["schemas"]["Settings"];
export type Packet = components["schemas"]["Packet"];
export type PacketCreate = components["schemas"]["PacketCreate"];
export type Run = components["schemas"]["Run"];
export type RunDetail = components["schemas"]["RunDetail"];
export type RunCreate = components["schemas"]["RunCreate"];
export type RunStatus = components["schemas"]["RunStatus"];

const client = createClient<paths>({ baseUrl: "/api/v1" });

/** Every non-2xx response is an RFC 7807 Problem whose `code` is fixed by the contract. */
export class ApiProblem extends Error {
  constructor(public problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

async function unwrap<T>(p: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await p;
  if (error !== undefined || data === undefined) {
    const e = error as Partial<Problem> | undefined;
    throw new ApiProblem({ type: "about:blank", title: e?.title ?? "Request failed", status: e?.status ?? 0, code: e?.code ?? "not_found", detail: e?.detail, violations: e?.violations });
  }
  return data;
}

export const api = {
  me: () => unwrap(client.GET("/me")),
  register: () => unwrap(client.GET("/register")),
  obligation: (id: string) => unwrap(client.GET("/obligations/{id}", { params: { path: { id } } })),
  revisions: () => unwrap(client.GET("/revisions")),
  settings: () => unwrap(client.GET("/settings")),
  createPacket: (body: PacketCreate) => unwrap(client.POST("/packets", { body })),
  startRun: (body: RunCreate) => unwrap(client.POST("/runs", { body })),
  runs: () => unwrap(client.GET("/runs", { params: { query: {} } })),
  run: (id: string) => unwrap(client.GET("/runs/{id}", { params: { path: { id } } })),
  diff: (from: string, to: string) => unwrap(client.GET("/revisions/{from}/diff/{to}", { params: { path: { from, to } } })),
};
