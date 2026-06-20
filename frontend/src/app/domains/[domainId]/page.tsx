import Link from "next/link";
import { api } from "@/lib/api";
import { MasteryBar } from "@/components/MasteryBar";

export const dynamic = "force-dynamic";

export default async function DomainOverview({
  params,
}: {
  params: Promise<{ domainId: string }>;
}) {
  const { domainId } = await params;

  let profile = null;
  let weakness = null;
  let graph = null;
  let error = "";

  try {
    [profile, weakness, graph] = await Promise.all([
      api.getProfile(domainId),
      api.getWeakness(domainId, 5),
      api.getDomain(domainId),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || !profile || !graph) {
    return (
      <div className="panel error">
        <strong>无法加载领域数据。</strong>请确认后端已启动(<code>deeptutor serve</code>)。
        <br />
        <small>{error}</small>
      </div>
    );
  }

  const s = profile.summary;
  const byModule = new Map<string, typeof graph.knowledge_points>();
  for (const kp of graph.knowledge_points) {
    const list = byModule.get(kp.module_id) ?? [];
    list.push(kp);
    byModule.set(kp.module_id, list);
  }
  const masteryById = new Map(profile.knowledge_points.map((r) => [r.knowledge_point_id, r.mastery]));

  return (
    <>
      {s.assessed === 0 ? (
        <div className="panel">
          <div className="domain-name">尚未建立学习档案</div>
          <p className="muted">
            完成一次入门诊断,系统将评估你在各知识点的水平,并据此规划个性化学习路线。
          </p>
          <form action={`/domains/${domainId}/diagnostic`} style={{ marginTop: 12 }}>
            <button type="submit">开始入门诊断 →</button>
          </form>
        </div>
      ) : (
        <div className="panel">
          <div className="domain-name">当前水平:{s.overall_level}</div>
          <div className="stat-grid" style={{ marginTop: 12 }}>
            <div className="stat">
              <div className="stat-value">{Math.round(s.average_mastery * 100)}%</div>
              <div className="stat-label">平均掌握度</div>
            </div>
            <div className="stat">
              <div className="stat-value">{s.assessed}/{s.total_knowledge_points}</div>
              <div className="stat-label">已评估知识点</div>
            </div>
            <div className="stat">
              <div className="stat-value">{s.mastered}</div>
              <div className="stat-label">已掌握(≥70%)</div>
            </div>
            <div className="stat">
              <div className="stat-value">{Math.round(s.coverage * 100)}%</div>
              <div className="stat-label">覆盖率</div>
            </div>
          </div>
        </div>
      )}

      {weakness && weakness.weak_points.length > 0 && (
        <>
          <h2>当前薄弱点</h2>
          <div className="panel">
            <ul className="clean">
              {weakness.weak_points.map((w) => (
                <li key={w.knowledge_point_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong>{w.name}</strong>
                    <span className="muted" style={{ marginLeft: 8 }}>
                      {w.correct}/{w.attempts} 正确
                    </span>
                  </div>
                  <MasteryBar mastery={w.mastery} />
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      <h2>知识图谱</h2>
      {graph.modules.map((m) => {
        const kps = byModule.get(m.id) ?? [];
        return (
          <div key={m.id} className="panel">
            <div className="domain-name">{m.name || m.id}</div>
            <ul className="clean" style={{ marginTop: 8 }}>
              {kps.map((kp) => {
                const mast = masteryById.get(kp.id);
                return (
                  <li key={kp.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
                    <div>
                      <strong>{kp.name}</strong>
                      {kp.prerequisites.length > 0 && (
                        <span className="muted" style={{ marginLeft: 8 }}>
                          依赖: {kp.prerequisites.join(", ")}
                        </span>
                      )}
                    </div>
                    {mast !== undefined ? (
                      <MasteryBar mastery={mast} />
                    ) : (
                      <span className="muted">未评估</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </>
  );
}
