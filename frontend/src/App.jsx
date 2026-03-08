import { useEffect, useMemo, useRef, useState } from "react";
import { Header } from "./components/Header";
import { ChatMessage, MediaPreview } from "./components/ChatMessage";
import { TypingIndicator } from "./components/TypingIndicator";
import { OpenWorldLogo } from "./components/OpenWorldLogo";
import { Sidebar } from "./components/Sidebar";
import { ProviderSettings } from "./components/ProviderSettings";

const API_BASE = "";

export function App() {
  const [sessionId, setSessionId] = useState("web_main");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sidebarTab, setSidebarTab] = useState("actions");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const chatRef = useRef(null);
  const textareaRef = useRef(null);

  const canSend = useMemo(() => input.trim().length > 0 && !loading, [input, loading]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, loading]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) send();
    }
  }

  async function send(directText) {
    const text = (directText || input).trim();
    if (!text) return;
    setInput("");
    setLoading(true);
    const now = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    setMessages((prev) => [...prev, { role: "user", content: text, timestamp: now }]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text, source: "web" }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || "Request failed");
      }
      const data = await res.json();
      const replyTime = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          timestamp: replyTime,
          toolsUsed: data.used_tools || [],
          media: data.media || [],
        },
      ]);
    } catch (err) {
      const errTime = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Hata: ${err.message}`, timestamp: errTime },
      ]);
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  function handleQuickAction(msg) {
    send(msg);
  }

  return (
    <div className={`app ${sidebarOpen ? "with-sidebar" : ""}`}>
      <Header sessionId={sessionId} onSessionChange={setSessionId}>
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarOpen((v) => !v)}
          title={sidebarOpen ? "Paneli Kapat" : "Paneli Aç"}
        >
          {sidebarOpen ? "◀" : "▶"}
        </button>
      </Header>

      <div className="app-body">
        {sidebarOpen && (
          <Sidebar
            activeTab={sidebarTab}
            onTabChange={setSidebarTab}
            onQuickAction={handleQuickAction}
            sessionId={sessionId}
            onSessionChange={setSessionId}
          />
        )}

        <div className="chat-area">
          {sidebarTab === "settings" ? (
            <ProviderSettings />
          ) : (
            <>
              <main className="chat" ref={chatRef}>
                {messages.length === 0 && !loading && <WelcomeScreen onSend={send} />}
                {messages.map((m, i) => (
                  <div key={i}>
                    <ChatMessage {...m} />
                    {m.media && <MediaPreview media={m.media} />}
                  </div>
                ))}
                {loading && <TypingIndicator />}
              </main>

              <footer className="composer">
                <textarea
                  ref={textareaRef}
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Mesajınızı yazın..."
                />
                <button disabled={!canSend} onClick={() => send()} aria-label="Gonder">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                </button>
              </footer>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function WelcomeScreen({ onSend }) {
  const hints = [
    "Bugünkü haberler nedir?",
    "Dolar kuru ne durumda?",
    "Görevlerimi listele",
  ];

  return (
    <div className="welcome">
      <OpenWorldLogo size={72} className="welcome-logo" />
      <h2>OpenWorld</h2>
      <p>Yerel otonom asistanınız. Bir soru sorun veya görev verin.</p>
      <div className="welcome-hints">
        {hints.map((text) => (
          <button key={text} className="hint" onClick={() => onSend(text)}>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
