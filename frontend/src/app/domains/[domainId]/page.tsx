import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DomainPage({
  params,
}: {
  params: Promise<{ domainId: string }>;
}) {
  const { domainId } = await params;
  let graph;
  let diagnostic;
  let error = "";

  try {
    graph = await api.getDomain(domainId);
    diagnostic = await api.startDiagnostic(domainId);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error) {
    return (
      <main className="container">
        <Link href="/" className="muted">
          ← 返回
        </Link>
        <div className="panel error">
          <strong>加载领域失败。</strong>
          <br />
          <small>{error}</small>
        </div>
      </main>
    );
  }

  if (!graph || !diagnostic) return null;

  // Group knowledge points by module for display.
  const byModule = new Map<string, typeof graph.knowledge_points>();
  for (const kp of graph.knowledge_points) {
    const list = byModule.get(kp.module_id) ?? [];
    list.push(kp);
    byModule.set(kp.module_id, list);
  }

  return (
    <main className="container">
      <Link href="/" className="muted">
        ← 返回领域列表
      </Link>

      <h1>{graph.name}</h1>
      <p className="subtitle">{graph.description}</p>

      <h2>入门诊断</h2>
      <div className="panel">
        <div>
          <span className="badge">题目数 {diagnostic.total_questions}</span>
          <span className="badge">
            默认难度 {diagnostic.blueprint.default_difficulty}
          </span>
          <span className="badge">
            每模块 {diagnostic.blueprint.questions_per_module} 题
          </span>
        </div>
        <p className="muted" style={{ marginTop: 12 }}>
          完成诊断后将建立你的能力基线,并据此规划个性化学习路线图。
          (诊断执行能力将在 Phase 1 落地)
        </p>
      </div>

      <h2>知识图谱</h2>
      {graph.modules.map((m) => {
        const kps = byModule.get(m.id) ?? [];
        return (
          <div key={m.id} className="panel">
            <div className="domain-name">{m.name || m.id}</div>
            <ul style={{ margin: "12px 0 0", paddingLeft: 20 }}>
              {kps.map((kp) => (
                <li key={kp.id}>
                  <strong>{kp.name}</strong>{" "}
                  <span className="muted">({kp.id})</span>
                  {kp.prerequisites.length > 0 && (
                    <span className="muted">
                      {" "}
                      · 依赖: {kp.prerequisites.join(", ")}
                    </span>
                  )}
                  {kp.summary && (
                    <div className="muted" style={{ fontSize: "0.9rem" }}>
                      {kp.summary}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </main>
  );
}
