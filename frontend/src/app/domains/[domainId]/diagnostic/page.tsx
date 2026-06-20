"use client";

import { use, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

/**
 * Interactive entry diagnostic. Flow:
 *   prepare → answer each question → submit all → see graded report.
 *
 * Client-side because it tracks per-question answers in React state and
 * needs a submit handler. Calls the REST endpoints directly from the browser
 * (same-origin via the rewrite proxy).
 */

type Stage = "idle" | "loading" | "answering" | "submitting" | "done";

interface Q {
  knowledge_point_id: string;
  question: string;
  expected_answer: string;
}

export default function DiagnosticPage({ params }: { params: Promise<{ domainId: string }> }) {
  const { domainId } = use(params);
  const [stage, setStage] = useState<Stage>("idle");
  const [questions, setQuestions] = useState<Q[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{ correct: number; total: number; pct: number; overall_level: string } | null>(null);
  const [error, setError] = useState("");

  async function start() {
    setStage("loading");
    setError("");
    try {
      const prep = await api.startDiagnostic(domainId);
      const qs: Q[] = prep.questions.map((q) => ({
        knowledge_point_id: q.knowledge_point_id,
        question: q.question,
        expected_answer: q.expected_answer ?? q.correct_answer ?? "",
      }));
      setQuestions(qs);
      setStage("answering");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("idle");
    }
  }

  async function submit() {
    setStage("submitting");
    setError("");
    try {
      const payload = questions.map((q) => {
        const ua = answers[q.knowledge_point_id] ?? "";
        // Client-side correctness: exact/contains match on the expected answer
        // for the placeholder generator's concept questions. The server BKT
        // update trusts this flag (same convention as DeepTutor quiz-results).
        const correct = ua.trim().length > 0 && q.expected_answer.toLowerCase().includes(ua.trim().toLowerCase());
        return { knowledge_point_id: q.knowledge_point_id, is_correct: correct };
      });
      const graded = await fetch(`/api/v1/personal/diagnostics/${domainId}/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: payload }),
      }).then((r) => r.json());
      setResult({
        correct: graded.score.correct,
        total: graded.score.total,
        pct: graded.score.pct,
        overall_level: graded.profile_summary?.overall_level ?? "?",
      });
      setStage("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("answering");
    }
  }

  if (stage === "idle") {
    return (
      <div className="panel">
        <div className="domain-name">入门诊断</div>
        <p className="muted" style={{ margin: "12px 0" }}>
          诊断会从知识图谱中抽样若干知识点,每点出一题。完成后建立你的能力基线,
          据此规划个性化学习路线。
        </p>
        <button onClick={start}>开始诊断</button>
        {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
      </div>
    );
  }

  if (stage === "loading" || stage === "submitting") {
    return <div className="panel muted">{stage === "loading" ? "正在准备题目..." : "正在判分..."}</div>;
  }

  if (stage === "done" && result) {
    return (
      <div className="panel">
        <div className="domain-name">诊断完成</div>
        <div className="stat-grid" style={{ marginTop: 12 }}>
          <div className="stat">
            <div className="stat-value">{result.correct}/{result.total}</div>
            <div className="stat-label">正确率 {Math.round(result.pct * 100)}%</div>
          </div>
          <div className="stat">
            <div className="stat-value">{result.overall_level}</div>
            <div className="stat-label">整体水平</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>
          学习档案已更新。前往档案页查看弱点,或生成个性化路线图。
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Link href={`/domains/${domainId}/profile`} className="nav-link">查看档案</Link>
          <Link href={`/domains/${domainId}/roadmap`} className="nav-link">生成路线图</Link>
        </div>
      </div>
    );
  }

  // answering
  return (
    <div>
      <div className="panel">
        <div className="domain-name">诊断中 · 共 {questions.length} 题</div>
        <p className="muted" style={{ marginTop: 4 }}>
          尽量作答;不确定的可以留空(计为错误)。完成后统一判分。
        </p>
      </div>
      {questions.map((q, i) => (
        <div key={q.knowledge_point_id} className="panel">
          <div className="muted" style={{ fontSize: "0.8rem" }}>
            Q{i + 1} · {q.knowledge_point_id}
          </div>
          <div style={{ margin: "8px 0" }}>{q.question}</div>
          <textarea
            placeholder="在此作答..."
            value={answers[q.knowledge_point_id] ?? ""}
            onChange={(e) => setAnswers({ ...answers, [q.knowledge_point_id]: e.target.value })}
          />
        </div>
      ))}
      <button onClick={submit} style={{ marginTop: 4 }}>提交全部答案</button>
      {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
    </div>
  );
}
