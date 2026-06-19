/**
 * PersonalTutor API client.
 *
 * Types mirror the FastAPI response shapes defined in
 * personal_tutor/api/router.py.
 *
 * URL resolution:
 *  - On the **server** (SSR / Server Components) we must use an absolute URL,
 *    because Next's `rewrites` only apply to browser requests. We read
 *    `DEEPTUTOR_API` (default http://localhost:8001).
 *  - On the **client** we use a relative path so the request goes through the
 *    same-origin rewrite proxy (no CORS in dev).
 */

function resolveBase(): string {
  // typeof window === "undefined" => server-side render / route handler.
  if (typeof window === "undefined") {
    const api = process.env.DEEPTUTOR_API || "http://localhost:8001";
    return `${api}/api/v1/personal`;
  }
  return "/api/v1/personal";
}

export interface HealthResponse {
  ok: boolean;
  personal_tutor_version: string;
  min_deeptutor_version: string;
  domains: string[];
}

export interface DomainSummary {
  domain_id: string;
  name: string;
  description: string;
  knowledge_point_count: number;
}

export interface KnowledgePoint {
  id: string;
  name: string;
  summary: string;
  type: string;
  module_id: string;
  prerequisites: string[];
  tags: string[];
}

export interface DomainGraph extends DomainSummary {
  modules: { id: string; name: string }[];
  module_names: Record<string, string[]>;
  knowledge_points: KnowledgePoint[];
  topological_order: string[];
}

export interface DiagnosticPlan {
  domain_id: string;
  blueprint: {
    questions_per_module: number;
    default_difficulty: string;
    must_include: string[];
  };
  question_plan: { knowledge_point_id: string; name: string }[];
  total_questions: number;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${resolveBase()}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${path}: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJson<HealthResponse>("/health"),
  listDomains: () => getJson<DomainSummary[]>("/domains"),
  getDomain: (id: string) => getJson<DomainGraph>(`/domains/${id}`),
  startDiagnostic: (id: string) =>
    fetch(`${resolveBase()}/diagnostics/${id}/start`, {
      method: "POST",
    }).then((r) => {
      if (!r.ok) throw new Error(`diagnostic start failed: ${r.status}`);
      return r.json() as Promise<DiagnosticPlan>;
    }),
};
