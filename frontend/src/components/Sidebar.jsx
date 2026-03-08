import { useEffect, useState } from "react";

const API_BASE = "";

const QUICK_ACTIONS = [
  { icon: "📰", label: "Haberler", msg: "Bugünkü haberleri özetle" },
  { icon: "📸", label: "Ekran", msg: "Masaüstü ekran görüntüsü al" },
  { icon: "📧", label: "Gmail", msg: "Gmail'imi kontrol et" },
  { icon: "📋", label: "Görevler", msg: "Görevlerimi listele" },
  { icon: "🔍", label: "Araştır", msg: "Detaylı araştırma yap: " },
  { icon: "📁", label: "Dosyalar", msg: "Desktop klasörünü listele" },
];

export function Sidebar({ activeTab, onTabChange, onQuickAction, sessionId, onSessionChange }) {
  const [sessions, setSessions] = useState([]);
  const [files, setFiles] = useState([]);
  const [notebooks, setNotebooks] = useState([]);
  const [filesPath, setFilesPath] = useState("");

  useEffect(() => {
    fetchSessions();
  }, []);

  async function fetchSessions() {
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch { /* ignore */ }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab ${activeTab === "actions" ? "active" : ""}`}
          onClick={() => onTabChange("actions")}
          title="Hızlı İşlemler"
        >⚡</button>
        <button
          className={`sidebar-tab ${activeTab === "sessions" ? "active" : ""}`}
          onClick={() => onTabChange("sessions")}
          title="Oturumlar"
        >💬</button>
        <button
          className={`sidebar-tab ${activeTab === "files" ? "active" : ""}`}
          onClick={() => onTabChange("files")}
          title="Dosyalar"
        >📂</button>
        <button
          className={`sidebar-tab ${activeTab === "settings" ? "active" : ""}`}
          onClick={() => onTabChange("settings")}
          title="Ayarlar"
        >⚙</button>
      </div>

      <div className="sidebar-content">
        {activeTab === "actions" && (
          <div className="sidebar-panel">
            <h3 className="sidebar-title">Hızlı İşlemler</h3>
            <div className="quick-actions">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  className="quick-action-btn"
                  onClick={() => onQuickAction(action.msg)}
                >
                  <span className="qa-icon">{action.icon}</span>
                  <span className="qa-label">{action.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {activeTab === "sessions" && (
          <div className="sidebar-panel">
            <h3 className="sidebar-title">Oturumlar</h3>
            <div className="session-list">
              {sessions.map((s) => (
                <button
                  key={s}
                  className={`session-item ${s === sessionId ? "active" : ""}`}
                  onClick={() => onSessionChange(s)}
                >
                  <span className="session-name">{s}</span>
                </button>
              ))}
              {sessions.length === 0 && (
                <p className="sidebar-empty">Henüz oturum yok</p>
              )}
            </div>
          </div>
        )}

        {activeTab === "files" && (
          <div className="sidebar-panel">
            <h3 className="sidebar-title">Çalışma Alanı</h3>
            <p className="sidebar-empty">
              Dosya tarayıcı aktif. Chat'ten "listele" komutunu kullanın.
            </p>
          </div>
        )}

        {activeTab === "settings" && (
          <div className="sidebar-panel">
            <h3 className="sidebar-title">Ayarlar</h3>
            <p className="sidebar-empty sidebar-settings-hint">
              LLM saglayici ayarlari ana panelde goruntuleniyordur.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
