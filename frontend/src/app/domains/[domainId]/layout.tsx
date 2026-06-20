import Link from "next/link";
import { api } from "@/lib/api";

/**
 * Shared layout for all domain sub-pages. Renders the domain header + a nav
 * rail (档案 / 路线图 / 练习 / 考试) so the learner can move between the
 * surfaces of one domain without losing context.
 *
 * `force-dynamic` because every child reads live learner state.
 */
export const dynamic = "force-dynamic";

const NAV = [
  { href: "", label: "概览" },
  { href: "/profile", label: "学习档案" },
  { href: "/roadmap", label: "路线图" },
  { href: "/practice", label: "练习" },
  { href: "/exam", label: "考试" },
];

export default async function DomainLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ domainId: string }>;
}) {
  const { domainId } = await params;
  let name = domainId;
  try {
    const d = await api.getDomain(domainId);
    name = d.name;
  } catch {
    /* header falls back to id if backend unreachable */
  }

  return (
    <main className="container">
      <Link href="/" className="muted">
        ← 全部领域
      </Link>
      <h1 style={{ marginTop: 8 }}>{name}</h1>
      <nav style={{ display: "flex", gap: 8, margin: "16px 0 24px", flexWrap: "wrap" }}>
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={`/domains/${domainId}${n.href}`}
            className="nav-link"
          >
            {n.label}
          </Link>
        ))}
      </nav>
      {children}
    </main>
  );
}
