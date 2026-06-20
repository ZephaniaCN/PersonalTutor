import { api } from "@/lib/api";
import { MasteryBar } from "@/components/MasteryBar";

export const dynamic = "force-dynamic";

/**
 * Learning profile page: the full per-KP mastery table, sorted weakest-first,
 * grouped by module. This is the "who am I as a learner" view that drives
 * every other decision (roadmap, quiz targeting, exam blueprint).
 */
export default async function ProfilePage({
  params,
}: {
  params: Promise<{ domainId: string }>;
}) {
  const { domainId } = await params;
  let profile = null;
  let error = "";
  try {
    profile = await api.getProfile(domainId);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || !profile) {
    return (
      <div className="panel error">
        <strong>暂无学习档案。</strong>请先完成一次入门诊断。
        <br />
        <small>{error}</small>
      </div>
    );
  }

  const s = profile.summary;
  // Group the (already weakest-sorted) rows by module for display.
  const byModule = new Map<string, typeof profile.knowledge_points>();
  for (const row of profile.knowledge_points) {
    const list = byModule.get(row.module_id) ?? [];
    list.push(row);
    byModule.set(row.module_id, list);
  }

  return (
    <>
      <div className="panel">
        <div className="domain-name">整体水平:{s.overall_level}</div>
        <div className="stat-grid" style={{ marginTop: 12 }}>
          <div className="stat"><div className="stat-value">{Math.round(s.average_mastery * 100)}%</div><div className="stat-label">平均掌握度</div></div>
          <div className="stat"><div className="stat-value">{s.coverage > 0 ? Math.round(s.coverage * 100) + "%" : "—"}</div><div className="stat-label">覆盖率</div></div>
          <div className="stat"><div className="stat-value">{s.mastered}/{s.total_knowledge_points}</div><div className="stat-label">已掌握</div></div>
        </div>
      </div>

      <h2>知识点掌握度(薄弱优先)</h2>
      {[...byModule.entries()].map(([moduleId, rows]) => (
        <div key={moduleId} className="panel">
          <div className="muted" style={{ fontSize: "0.8rem", marginBottom: 8 }}>{moduleId}</div>
          <ul className="clean">
            {rows.map((r) => (
              <li key={r.knowledge_point_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
                <div>
                  <strong>{r.name}</strong>
                  <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>
                    {r.attempts > 0 ? `${r.correct}/${r.attempts} 正确` : "未评估"}
                  </span>
                </div>
                <MasteryBar mastery={r.mastery} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
