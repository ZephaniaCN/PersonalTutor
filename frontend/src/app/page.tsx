import { api } from "@/lib/api";
import type { DomainSummary, HealthResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let health: HealthResponse | null = null;
  let domains: DomainSummary[] = [];
  let error = "";

  try {
    [health, domains] = await Promise.all([api.health(), api.listDomains()]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="container">
      <h1>PersonalTutor</h1>
      <p className="subtitle">
        基于 DeepTutor 的个性化学习导师系统
      </p>

      {error ? (
        <div className="panel error">
          <strong>无法连接后端。</strong>请确认 DeepTutor 服务已启动(
          <code>deeptutor serve</code>,默认端口 8001)。
          <br />
          <small>{error}</small>
        </div>
      ) : health ? (
        <div className="panel">
          <span className={`badge ${health.ok ? "ok" : ""}`}>
            {health.ok ? "在线" : "异常"}
          </span>
          <span className="badge">PersonalTutor v{health.personal_tutor_version}</span>
          <span className="badge">DeepTutor ≥ {health.min_deeptutor_version}</span>
        </div>
      ) : null}

      <h2>学习领域</h2>
      {domains.length === 0 ? (
        <p className="muted">尚未注册任何领域。</p>
      ) : (
        domains.map((d) => (
          <div key={d.domain_id} className="panel domain-card">
            <div>
              <div className="domain-name">{d.name}</div>
              <div className="muted">
                {d.description} · {d.knowledge_point_count} 个知识点
              </div>
            </div>
            <form action={`/domains/${d.domain_id}`} style={{ margin: 0 }}>
              <button type="submit">进入</button>
            </form>
          </div>
        ))
      )}
    </main>
  );
}
