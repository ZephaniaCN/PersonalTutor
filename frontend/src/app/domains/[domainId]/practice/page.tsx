"use client";

import { use, useState } from "react";
import { api, type QuizNext, type QuizGrade } from "@/lib/api";
import { MasteryBar } from "@/components/MasteryBar";

/**
 * Adaptive practice loop. Each round:
 *   fetch the weakest KP's question → learner answers → grade → show verdict
 *   + updated mastery → "next" fetches a fresh question targeting the new
 *   weakest point.
 *
 * The mastery shown updates live after each grade, so the learner sees their
 * estimate sharpen in real time — the feedback loop that makes adaptive
 * practice effective.
 */

export default function PracticePage({ params }: { params: Promise<{ domainId: string }> }) {
  const { domainId } = use(params);
  const [question, setQuestion] = useState<QuizNext | null>(null);
  const [answer, setAnswer] = useState("");
  const [verdict, setVerdict] = useState<QuizGrade | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(0); // count answered this session

  async function fetchNext() {
    setLoading(true);
    setError("");
    setVerdict(null);
    setAnswer("");
    try {
      const q = await api.quizNext(domainId);
      setQuestion(q);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function grade() {
    if (!question) return;
    setLoading(true);
    setError("");
    try {
      const g = await api.quizGrade(domainId, {
        knowledge_point_id: question.knowledge_point_id,
        user_answer: answer,
        question: question.question,
      });
      setVerdict(g);
      setDone((d) => d + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  if (!question && !verdict) {
    return (
      <div className="panel">
        <div className="domain-name">自适应练习</div>
        <p className="muted" style={{ margin: "12px 0" }}>
          每次取你最薄弱的知识点出题,难度随掌握度自动调整。答完后立即判分并更新档案。
        </p>
        <button onClick={fetchNext} disabled={loading}>开始练习</button>
        {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
      </div>
    );
  }

  return (
    <div>
      {question && !verdict && (
        <div className="panel">
          <div className="muted" style={{ fontSize: "0.8rem" }}>
            {question.kp_name} · 难度 {question.difficulty} · {question.rationale}
          </div>
          <div style={{ margin: "12px 0", fontSize: "1.05rem" }}>{question.question.question}</div>
          <textarea
            placeholder="在此作答..."
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={loading}
          />
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button onClick={grade} disabled={loading || !answer.trim()}>提交答案</button>
            <button onClick={fetchNext} disabled={loading} className="nav-link">跳过</button>
          </div>
        </div>
      )}

      {verdict && (
        <div className="panel">
          <div className={verdict.verdict.is_correct ? "verdict-correct" : "verdict-wrong"} style={{ fontSize: "1.1rem" }}>
            {verdict.verdict.is_correct ? "✓ 回答正确" : "✗ 不完全正确"}
          </div>
          <div className="muted" style={{ marginTop: 4 }}>
            得分 {Math.round(verdict.verdict.score * 100)}% · {verdict.verdict.rationale}
            {verdict.verdict.method === "fallback" && " (回退判分,配置 LLM 可获更准判定)"}
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: "0.8rem", marginBottom: 4 }}>
              掌握度更新: <MasteryBar mastery={verdict.new_mastery} />
            </div>
          </div>
          <div style={{ marginTop: 12, padding: 12, background: "var(--bg)", borderRadius: 6 }}>
            <div className="muted" style={{ fontSize: "0.8rem" }}>参考答案</div>
            <div style={{ marginTop: 4 }}>{verdict.expected_answer}</div>
          </div>
          <button onClick={fetchNext} disabled={loading} style={{ marginTop: 12 }}>下一题 →</button>
        </div>
      )}

      {done > 0 && <div className="muted" style={{ textAlign: "center", marginTop: 16 }}>本次已练习 {done} 题</div>}
      {error && <div className="error" style={{ marginTop: 12 }}><small>{error}</small></div>}
      {loading && <div className="muted" style={{ marginTop: 8 }}>处理中...</div>}
    </div>
  );
}
