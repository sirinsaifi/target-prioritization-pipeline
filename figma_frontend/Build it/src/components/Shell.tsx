import { NavLink, Outlet, useLocation } from "react-router-dom";
import { DISEASE } from "../data/demo";

const NAV_ITEMS = [
  { to: "/setup", label: "Analysis", icon: "⬡", group: "input" },
  { to: "/results", label: "Evidence", icon: "◈", group: "evidence" },
  { to: "/results", label: "Verification", icon: "✦", group: "verification" },
  { to: "/results", label: "Results", icon: "◉", group: "results" },
  { to: "/why/SOD1", label: "Explainability", icon: "◎", group: "explain" },
  { to: "/gaps/SOD1", label: "Research Gaps", icon: "◌", group: "gaps" },
  { to: "/network/SOD1", label: "Network", icon: "⬡", group: "network" },
  { to: "/comparison", label: "Comparison", icon: "⊞", group: "comparison" },
  { to: "/report/SOD1", label: "Reports", icon: "▤", group: "reports" },
];

export default function Shell() {
  const location = useLocation();

  const activeGroup = NAV_ITEMS.find((item) => location.pathname.startsWith(item.to))?.group ?? "";

  return (
    <div className="flex h-full bg-[var(--bg)]">
      {/* Sidebar */}
      <aside
        style={{
          width: 220,
          minWidth: 220,
          borderRight: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
          padding: "0",
        }}
      >
        {/* Logo */}
        <div style={{ padding: "20px 20px 16px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 7,
                background: "linear-gradient(135deg, #a596d5, #8b7fd1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 14,
                color: "white",
              }}
            >
              ◈
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-primary)" }}>
                EVIDENS
              </div>
              <div style={{ fontSize: 9.5, color: "var(--text-muted)", letterSpacing: "0.06em" }}>
                ALS Intelligence Platform
              </div>
            </div>
          </div>
        </div>

        {/* Disease context */}
        <div
          style={{
            margin: "12px 12px 8px",
            padding: "10px 12px",
            borderRadius: 8,
            background: "var(--brand-gradient-subtle)",
            border: "1px solid #e4ddf4",
          }}
        >
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 2 }}>
            ACTIVE INVESTIGATION
          </div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-primary)" }}>{DISEASE.shortName}</div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>{DISEASE.ontologyId}</div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "4px 8px", overflowY: "auto" }}>
          {NAV_ITEMS.map((item, i) => {
            const isActive = location.pathname === item.to || (item.to !== "/setup" && location.pathname.startsWith(item.to));
            return (
              <NavLink
                key={i}
                to={item.to}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "7px 10px",
                  borderRadius: 7,
                  marginBottom: 2,
                  textDecoration: "none",
                  fontSize: 12.5,
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? "#8b7fd1" : "var(--text-secondary)",
                  background: isActive ? "rgba(139,127,209,0.09)" : "transparent",
                  transition: "all 0.15s",
                  letterSpacing: "0.01em",
                }}
              >
                <span style={{ fontSize: 10, opacity: 0.7 }}>{item.icon}</span>
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Bottom status */}
        <div
          style={{
            padding: "12px 16px",
            borderTop: "1px solid var(--border)",
            fontSize: 10.5,
            color: "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          Analysis complete — 5 targets
        </div>
      </aside>

      {/* Main content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Top bar */}
        <header
          style={{
            height: 52,
            borderBottom: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            alignItems: "center",
            padding: "0 24px",
            gap: 16,
            flexShrink: 0,
          }}
        >
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 20 }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>
              {DISEASE.name}
            </span>
            <span style={{ width: 1, height: 16, background: "var(--border)" }} />
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 600,
                letterSpacing: "0.06em",
                color: "#22c55e",
                background: "rgba(34,197,94,0.08)",
                padding: "2px 8px",
                borderRadius: 4,
              }}
            >
              ANALYSIS COMPLETE
            </span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>5 candidate targets · Run 2026-09-10 08:32 UTC</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => window.location.href = "/"}
              style={{
                fontSize: 11.5,
                padding: "5px 12px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              New Analysis
            </button>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, overflowY: "auto" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
