import { api } from "@/lib/api";
import { MasteryBar } from "@/components/MasteryBar";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

/**
 * Server Action: generate the roadmap, then re-render this page so the freshly
 * built plan shows immediately. Kept inline because it closes over domainId
 * from the page params and must run on the server (it calls the backend).
 */
async function generateRoadmap(domainId: string) {
  "use server";
  await api.generateRoadmap(domainId);
  revalidatePath(`/domains/${domainId}/roadmap`);
}

/**
 * Personalized roadmap page. Shows the ordered objective list (weakest-first,
 * prereq-respecting) with each step's rationale, plus the already-acquired KPs.
 *
 * If no roadmap exists yet, offers a one-click generate button (POST) — but
 * since this is a Server Component, the generate is a small form posting to an
 * API route. For the MVP we link to a client generate action via a form that
 * targets the same page after a query-param trigger handled below.
 */
export default async function RoadmapPage({
  params,
}: {
  params: Promise<{ domainId: string }>;
}) {
  const { domainId } = await params;
  let roadmap = null;
  let error = "";
  try {
    roadmap = await api.getRoadmap(domainId);
  } catch {
    // 404 means "not generated yet" — show the generate CTA.
  }

  if (!roadmap) {
    const generate = generateRoadmap.bind(null, domainId);
    return (
      <div className="panel">
        <div className="domain-name">尚未生成路线图</div>
        <p className="muted" style={{ margin: "12px 0" }}>
          基于你的学习档案,系统会规划一条个性化路线:优先攻克薄弱知识点,
          并尊重知识图谱的前置依赖关系。
        </p>
        <form action={generate}>
          <button type="submit">生成个性化路线图</button>
        </form>
      </div>
    );
  }

  return (
    <>
      <div className="panel">
        <div className="domain-name">学习目标</div>
        <p className="muted" style={{ marginTop: 4 }}>{roadmap.goal}</p>
        <div className="stat-grid" style={{ marginTop: 12 }}>
          <div className="stat"><div className="stat-value">{roadmap.summary.remaining}</div><div className="stat-label">待学知识点</div></div>
          <div className="stat"><div className="stat-value">{roadmap.summary.acquired}</div><div className="stat-label">已掌握</div></div>
          <div className="stat"><div className="stat-value">{Math.round(roadmap.summary.average_mastery * 100)}%</div><div className="stat-label">平均掌握度</div></div>
        </div>
      </div>

      <h2>推荐学习顺序</h2>
      {roadmap.objectives.map((o) => (
        <div key={o.knowledge_point_id} className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <span className="badge">第 {o.order} 步</span>
              <strong style={{ marginLeft: 8, fontSize: "1.05rem" }}>{o.name}</strong>
              <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>{o.module_id}</span>
            </div>
            <MasteryBar mastery={o.mastery} />
          </div>
          <div className="muted" style={{ marginTop: 8 }}>{o.rationale}</div>
          {o.prerequisites.length > 0 && (
            <div className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>
              前置: {o.prerequisites.join(", ")}
            </div>
          )}
        </div>
      ))}

      {roadmap.acquired.length > 0 && (
        <>
          <h2>已掌握(已跳过)</h2>
          <div className="panel">
            <ul className="clean">
              {roadmap.acquired.map((a) => (
                <li key={a.knowledge_point_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>{a.name}</span>
                  <MasteryBar mastery={a.mastery} />
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </>
  );
}
