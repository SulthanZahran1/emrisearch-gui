interface LoadingStateProps {
  detail?: boolean;
}

export function LoadingState({ detail = false }: LoadingStateProps) {
  return (
    <div className="loading-state" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading {detail ? "run details" : "runs"}</span>
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-line" />
      <div className="skeleton-grid">
        {Array.from({ length: detail ? 8 : 4 }, (_, index) => (
          <div className="skeleton skeleton-cell" key={index} />
        ))}
      </div>
      {detail && <div className="skeleton skeleton-table" />}
    </div>
  );
}

interface StatePanelProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  tone?: "neutral" | "error";
}

export function StatePanel({
  title,
  message,
  actionLabel,
  onAction,
  tone = "neutral",
}: StatePanelProps) {
  return (
    <section className={`state-panel state-panel-${tone}`} role={tone === "error" ? "alert" : undefined}>
      <h1>{title}</h1>
      <p>{message}</p>
      {actionLabel && onAction && (
        <button type="button" className="button button-primary state-action" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </section>
  );
}
