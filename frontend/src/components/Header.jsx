import { OpenWorldLogo } from "./OpenWorldLogo";

export function Header({ sessionId, onSessionChange, children }) {
  return (
    <header className="header">
      <div className="header-brand">
        {children}
        <OpenWorldLogo size={34} />
        <h1>OpenWorld</h1>
        <span className="header-badge">Yerel Ajan</span>
      </div>
      <div className="header-session" title="Oturum kimliği — farklı sohbet geçmişleri için değiştirin">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
        <input
          className="session-input"
          value={sessionId}
          onChange={(e) => onSessionChange(e.target.value)}
          placeholder="Oturum adı"
        />
      </div>
    </header>
  );
}
