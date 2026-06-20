"use client";

import { use, useEffect, useState } from "react";
import { api, type ExamPaper, type ExamReport } from "@/lib/api";

/**
 * Formal exam flow: start (timed) → answer all → submit once → score report.
 *
 * Key UX differences from practice: a live countdown (because exams are
 * timed), no per-question feedback (one-shot, no answer leakage), and a
 * single submit that grades everything at once and produces a full report.
 */

type Stage = "idle" | "taking" | "submitting" | "done";

export default function ExamPage({ params }: { params: Promise<{ domainId: string }> }) {
  const { domainId } = use(params);
  const [stage, setStage] = useState<Stage>("idle");
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [report, setReport] = useState<ExamReport | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  // Live countdown tick.
  useEffect(() => {
    if (stage !== "taking" || !paper) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [stage, paper]);

  const deadlineMs = paper ? Date.parse(paper.deadline_iso) : 0;
  const remainSec = Math.max(0, Math.floor((deadlineMs - now) / 1000));
  const overtime = remainSec <= 0;

  async function start() {
    setError("");
    try {
      const p = await api.examStart(domainId, { num_questions: 10, duration_minutes: 30 });
      setPaper(p);
      setStage("taking");
      setNow(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function submit() {
    if (!paper) return;
    setStage("submitting");
    setError("");
    try {
      const payload = paper.questions.map((q) => ({
        knowledge_point_id: q.knowledge_point_id,
        user_answer: answers[q.knowledge_point_id] ?? "",
      }));
      const r = await api.examSubmit(paper.exam_id, payload);
      setReport(r);
      setStage("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("taking");
    }
  }

  // Auto-submit when time runs out.
  useEffect(() => {
    if (stage === "taking" && overtime && paper) {
      submit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overtime, stage]);

  if (stage === "idle") {
    return (
      <div className="panel">
        <div className="domain-name">正式考试</div>
        <p className="muted" style={{ margin: "12px 0" }}>
          一次性、限时 30 分钟、共 10 题。提交后统一判分并生成成绩单,
          答题期间不提供即时反馈。考试结果也会更新你的学习档案。
        </p>
        <button onClick={start}>开始考试</button>
        {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
      </div>
    );
  }

  if (stage === "submitting") {
    return <div className="panel muted">正在判分,请稍候...</div>;
  }

  if (stage === "done" && report) {
    const pct = Math.round(report.score.pct * 100);
    return (
      <div>
        <div className="panel">
          <div className="domain-name">考试完成</div>
          <div className="stat-grid" style={{ marginTop: 12 }}>
            <div className="stat"><div className="stat-value">{report.score.correct}/{report.score.total}</div><div className="stat-label">得分 {pct}%</div></div>
            <div className="stat"><div className="stat-value">{report.late ? "逾期" : "准时"}</div><div className="stat-label">提交状态</div></div>
            <div className="stat"><div className="stat-value">{report.profile_summary?.overall_level ?? "?"}</div><div className="stat-label">最新水平</div></div>
          </div>
        </div>

        <h2>逐题详情</h2>
        {report.per_kp?.map((p, i) => (
          <div key={p.knowledge_point_id} className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="muted" style={{ fontSize: "0.8rem" }}>Q{i + 1} · {p.knowledge_point_id}</span>
              <span className={p.verdict.is_correct ? "verdict-correct" : "verdict-wrong"}>
                {p.verdict.is_correct ? "✓" : "✗"} {Math.round(p.verdict.score * 100)}%
              </span>
            </div>
            <div style={{ marginTop: 8 }}><strong>你的答案:</strong> {p.user_answer || "(未作答)"}</div>
            <div className="muted" style={{ marginTop: 4 }}><strong>参考答案:</strong> {p.expected_answer}</div>
            <div className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>{p.verdict.rationale}</div>
          </div>
        ))}
      </div>
    );
  }

  // taking
  const mm = String(Math.floor(remainSec / 60)).padStart(2, "0");
  const ss = String(remainSec % 60).padStart(2, "0");
  const answered = paper ? paper.questions.filter((q) => (answers[q.knowledge_point_id] ?? "").trim()).length : 0;

  return (
    <div>
      <div className="panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>{paper?.title}</strong>
          <span className="muted" style={{ marginLeft: 8 }}>已答 {answered}/{paper?.num_questions}</span>
        </div>
        <div className={overtime ? "verdict-wrong" : ""} style={{ fontSize: "1.3rem", fontFamily: "monospace" }}>
          ⏱ {mm}:{ss}
        </div>
      </div>
      {paper?.questions.map((q, i) => (
        <div key={q.knowledge_point_id} className="panel">
          <div className="muted" style={{ fontSize: "0.8rem" }}>Q{i + 1} · {q.knowledge_point_id} · {q.difficulty}</div>
          <div style={{ margin: "8px 0" }}>{q.question}</div>
          <textarea
            placeholder="作答..."
            value={answers[q.knowledge_point_id] ?? ""}
            onChange={(e) => setAnswers({ ...answers, [q.knowledge_point_id]: e.target.value })}
          />
        </div>
      ))}
      <button onClick={submit} disabled={stage !== "taking"}>交卷</button>
      {overtime && <div className="verdict-wrong" style={{ marginTop: 8 }}>时间到,自动提交中...</div>}
      {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
    </div>
  );
}
