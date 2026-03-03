export function TypingIndicator() {
  return (
    <div className="message assistant">
      <div className="message-header">
        <span className="message-role">OpenWorld</span>
      </div>
      <div className="typing-indicator">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>
    </div>
  );
}
