import type { ReactNode } from "react";

interface AppShellProps {
  rail: ReactNode;
  children: ReactNode;
  theme: "dark" | "light";
  hasRun: boolean;
  view: "explorer" | "config-builder";
  onToggleTheme: () => void;
  onToggleView: () => void;
}

const sections = [
  ["manifest", "manifest"],
  ["best", "best point"],
  ["plots", "plots"],
] as const;

export function AppShell({ rail, children, theme, hasRun, view, onToggleTheme, onToggleView }: AppShellProps) {
  function scrollToSection(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="app-shell">
      {rail}
      <main className="main-column">
        <header className="main-header">
          <nav className="section-nav" aria-label="Run sections">
            <button
              key="view"
              type="button"
              className={`section-nav-button${view === "config-builder" ? " active" : ""}`}
              onClick={onToggleView}
            >
              config builder
            </button>
            {view === "explorer" && sections.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className="section-nav-button"
                disabled={!hasRun}
                onClick={() => scrollToSection(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <button
            type="button"
            className="button button-ghost theme-button"
            onClick={onToggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "light" : "dark"}
          </button>
        </header>
        <div className="content-column">{children}</div>
      </main>
    </div>
  );
}
