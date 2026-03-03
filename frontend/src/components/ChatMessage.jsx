import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

const TOOL_LABELS = {
  search_news: "Haber Arama",
  fetch_web_page: "Web Sayfa",
  read_text_file: "Dosya Oku",
  write_text_file: "Dosya Yaz",
  list_dir: "Klasör Listele",
  run_shell: "Komut",
  add_task: "Görev Ekle",
  list_tasks: "Görevler",
  complete_task: "Görev Tamamla",
  add_calendar_event: "Takvim",
  list_calendar_events: "Takvim",
  create_email_draft: "E-posta",
  research_and_report: "Araştırma",
  check_gmail_messages: "Gmail",
  check_outlook_messages: "Outlook",
};

export function ChatMessage({ role, content, timestamp, toolsUsed }) {
  const isUser = role === "user";

  return (
    <div className={`message ${role}`}>
      <div className="message-header">
        <span className="message-role">{isUser ? "Sen" : "OpenWorld"}</span>
        {timestamp && <span className="message-time">{timestamp}</span>}
      </div>
      <div className="message-body">
        {isUser ? (
          <p>{content}</p>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="table-wrap">
                  <table>{children}</table>
                </div>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        )}
      </div>
      {toolsUsed && toolsUsed.length > 0 && (
        <div className="message-tools">
          {toolsUsed.map((tool) => (
            <span key={tool} className="tool-badge">
              {TOOL_LABELS[tool] || tool}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
