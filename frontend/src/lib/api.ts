/**
 * PersonalTutor API client.
 *
 * Covers every /api/v1/personal/* endpoint the backend exposes. Types mirror
 * the FastAPI response shapes in personal_tutor/api/router.py.
 *
 * URL resolution: server-side (SSR) uses DEEPTUTOR_API (absolute, since Next
 * rewrites only apply to browser requests); client-side uses a relative path
 * through the same-origin rewrite proxy.
 */

function resolveBase(): string {
  if (typeof window === "undefined") {
    const api = process.env.DEEPTUTOR_API || "http://localhost:8001";
    return `${api}/api/v1/personal`;
  }
  return "/api/v1/personal";
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${resolveBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${resolveBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //

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

export interface ProfileSummary {
  total_knowledge_points: number;
  assessed: number;
  coverage: number;
  average_mastery: number;
  mastered: number;
  overall_level: string;
}

export interface ProfileRow {
  knowledge_point_id: string;
  name: string;
  module_id: string;
  mastery: number;
  level: string;
  attempts: number;
  correct: number;
}

export interface Profile {
  domain_id: string;
  generated_at: string;
  summary: ProfileSummary;
  weak_points: ProfileRow[];
  knowledge_points: ProfileRow[];
}

export interface WeaknessItem {
  knowledge_point_id: string;
  name: string;
  module_id: string;
  mastery: number;
  attempts: number;
  correct: number;
}

export interface Objective {
  order: number;
  knowledge_point_id: string;
  name: string;
  module_id: string;
  mastery: number;
  rationale: string;
  prerequisites: string[];
}

export interface Roadmap {
  domain_id: string;
  domain_name: string;
  goal: string;
  generated_at: string;
  summary: { total_knowledge_points: number; acquired: number; remaining: number; average_mastery: number };
  objectives: Objective[];
  acquired: { knowledge_point_id: string; name: string; mastery: number }[];
}

export interface ReviewItem {
  knowledge_point_id: string;
  name: string;
  module_id: string;
  due_at: number;
  retrievability: number;
  kind: string;
}

export interface QuizNext {
  domain_id: string;
  knowledge_point_id: string;
  kp_name: string;
  mastery: number;
  difficulty: string;
  rationale: string;
  question: {
    question_id?: string;
    knowledge_point_id?: string;
    question_type?: string;
    question: string;
    options?: string[];
    difficulty?: string;
    expected_answer?: string;
    explanation?: string;
  };
}

export interface GradeVerdict {
  is_correct: boolean;
  score: number;
  rationale: string;
  method: string;
}

export interface QuizGrade {
  domain_id: string;
  knowledge_point_id: string;
  verdict: GradeVerdict;
  new_mastery: number;
  expected_answer: string;
  explanation: string;
}

export interface ExamPaper {
  exam_id: string;
  domain_id: string;
  title: string;
  status: string;
  started_at_iso: string;
  deadline_iso: string;
  duration_minutes: number;
  num_questions: number;
  questions: {
    question_id?: string;
    knowledge_point_id: string;
    question_type?: string;
    question: string;
    options?: string[];
    difficulty?: string;
  }[];
}

export interface ExamReport {
  exam_id: string;
  domain_id: string;
  title: string;
  status: string;
  score: { correct: number; total: number; pct: number };
  late: boolean;
  submitted_at_iso?: string;
  per_kp?: { knowledge_point_id: string; verdict: GradeVerdict; user_answer: string; expected_answer: string }[];
  weak_points?: WeaknessItem[];
  profile_summary?: ProfileSummary;
}

// --------------------------------------------------------------------------- //
// API surface
// --------------------------------------------------------------------------- //

export const api = {
  health: () => getJson<HealthResponse>("/health"),
  listDomains: () => getJson<DomainSummary[]>("/domains"),
  getDomain: (id: string) => getJson<DomainGraph>(`/domains/${id}`),

  getProfile: (id: string) => getJson<Profile>(`/profile/${id}`),
  getWeakness: (id: string, limit = 10) => getJson<{ domain_id: string; weak_points: WeaknessItem[]; total: number }>(`/weakness/${id}?limit=${limit}`),

  startDiagnostic: (id: string) =>
    postJson<{
      diagnostic_id: string;
      domain_id: string;
      total_questions: number;
      questions: {
        knowledge_point_id: string;
        question: string;
        expected_answer?: string;
        correct_answer?: string;
        question_type?: string;
        difficulty?: string;
        explanation?: string;
        options?: string[];
      }[];
    }>(`/diagnostics/${id}/start`),

  getRoadmap: (id: string) => getJson<Roadmap>(`/roadmaps/${id}`),
  generateRoadmap: (id: string, goal?: string) => postJson(`/roadmaps/${id}/generate`, { goal, max_objectives: 50 }),

  getReviewQueue: (id: string, limit = 20) => getJson<{ domain_id: string; due_count: number; items: ReviewItem[] }>(`/review/${id}/queue?limit=${limit}`),

  quizNext: (id: string, exclude: string[] = []) => postJson<QuizNext>(`/quiz/${id}/next`, { exclude }),
  quizGrade: (id: string, body: { knowledge_point_id: string; user_answer: string; question?: unknown }) =>
    postJson<QuizGrade>(`/quiz/${id}/grade`, body),

  examStart: (id: string, opts: { num_questions?: number; duration_minutes?: number } = {}) =>
    postJson<ExamPaper>(`/exams/${id}/start`, opts),
  examSubmit: (examId: string, answers: { knowledge_point_id: string; user_answer: string }[]) =>
    postJson<ExamReport>(`/exams/${examId}/submit`, { answers }),
  examReport: (examId: string) => getJson<ExamReport>(`/exams/${examId}/report`),
};
