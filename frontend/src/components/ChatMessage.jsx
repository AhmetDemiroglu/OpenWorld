import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

const TOOL_LABELS = {
  // Web & Haber
  search_news: "Haber Arama",
  fetch_web_page: "Web Sayfa",
  research_and_report: "Araştırma",
  compare_topics: "Karşılaştırma",
  // Dosya
  read_text_file: "Dosya Oku",
  write_text_file: "Dosya Yaz",
  list_dir: "Klasör Listele",
  run_shell: "Komut",
  // Görev & Takvim
  add_task: "Görev Ekle",
  list_tasks: "Görevler",
  complete_task: "Görev Tamamla",
  add_calendar_event: "Takvim",
  list_calendar_events: "Takvim",
  // E-posta
  create_email_draft: "E-posta",
  check_gmail_messages: "Gmail",
  check_outlook_messages: "Outlook",
  // Not Defteri
  notebook_create: "Not Defteri",
  notebook_add_note: "Not Ekle",
  notebook_complete_step: "Adım Tamamla",
  notebook_status: "Not Durumu",
  notebook_list: "Defterler",
  notebook_add_step: "Adım Ekle",
  // Git & Kod
  git_status: "Git Durum",
  git_diff: "Git Diff",
  git_log: "Git Log",
  git_commit: "Git Commit",
  git_branch: "Git Branch",
  find_symbols: "Sembol Ara",
  code_search: "Kod Ara",
  refactor_rename: "Yeniden Adlandır",
  run_tests: "Test Çalıştır",
  // VS Code & AI
  vscode_command: "VS Code",
  claude_code_ask: "Claude Code",
  // Hafıza
  memory_store: "Hafıza Kaydet",
  memory_recall: "Hafıza Hatırla",
  memory_stats: "Hafıza İstatistik",
  // Office
  create_pdf: "PDF Oluştur",
  create_docx: "Word Oluştur",
  read_pdf: "PDF Oku",
  // Ekran
  screenshot: "Ekran Görüntüsü",
  open_in_vscode: "VS Code Aç",
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

/* Inline media preview for images embedded in messages */
export function MediaPreview({ media }) {
  if (!media || media.length === 0) return null;
  return (
    <div className="media-preview">
      {media.map((m, i) => {
        if (m.type === "image") {
          return (
            <a key={i} href={m.url} target="_blank" rel="noopener noreferrer" className="media-item media-image">
              <img src={m.url} alt={m.filename} loading="lazy" />
              <span className="media-caption">{m.filename}</span>
            </a>
          );
        }
        const icons = { audio: "\uD83C\uDFB5", video: "\uD83C\uDFA5", document: "\uD83D\uDCC4" };
        return (
          <a key={i} href={m.url} target="_blank" rel="noopener noreferrer" className="media-item media-file">
            <span className="media-file-icon">{icons[m.type] || "\uD83D\uDCC1"}</span>
            <span className="media-file-name">{m.filename}</span>
          </a>
        );
      })}
    </div>
  );
}
