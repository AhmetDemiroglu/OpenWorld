import { useEffect, useState, useCallback } from "react";

const API_BASE = "";

export function ProviderSettings() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(null); // provider id being tested
  const [testResults, setTestResults] = useState({}); // {id: {ok, message}}
  const [editState, setEditState] = useState({}); // {id: {field: value}}
  const [showKeys, setShowKeys] = useState({}); // {id: bool}
  const [saving, setSaving] = useState(null);

  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/providers`);
      const data = await res.json();
      setProviders(data.providers || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  function getEditValue(id, field) {
    if (editState[id] && editState[id][field] !== undefined) {
      return editState[id][field];
    }
    const p = providers.find((p) => p.id === id);
    return p ? p[field] || "" : "";
  }

  function setEditField(id, field, value) {
    setEditState((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || {}), [field]: value },
    }));
  }

  function hasUnsavedChanges(id) {
    const edits = editState[id];
    if (!edits) return false;
    const p = providers.find((p) => p.id === id);
    if (!p) return false;
    return Object.entries(edits).some(([k, v]) => (p[k] || "") !== v);
  }

  async function saveProvider(id) {
    const edits = editState[id];
    if (!edits) return;
    setSaving(id);
    try {
      const res = await fetch(`${API_BASE}/providers/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(edits),
      });
      if (res.ok) {
        setEditState((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        await fetchProviders();
      }
    } catch {
      /* ignore */
    } finally {
      setSaving(null);
    }
  }

  async function testConnection(id) {
    setTesting(id);
    setTestResults((prev) => ({ ...prev, [id]: null }));
    try {
      const res = await fetch(`${API_BASE}/providers/${id}/test`, { method: "POST" });
      const data = await res.json();
      setTestResults((prev) => ({ ...prev, [id]: data }));
    } catch (e) {
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message: "Istek gonderilemedi." } }));
    } finally {
      setTesting(null);
    }
  }

  async function setActive(id) {
    try {
      await fetch(`${API_BASE}/providers/active`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: id }),
      });
      await fetchProviders();
    } catch {
      /* ignore */
    }
  }

  function getStatusBadge(p) {
    if (p.is_active) {
      return { cls: "badge-active", text: "Aktif" };
    }
    if (p.type === "ollama") {
      return { cls: "badge-local", text: "Yerel" };
    }
    if (p.api_key) {
      return { cls: "badge-ready", text: "API Key girilmis" };
    }
    return { cls: "badge-unconfigured", text: "Yapilandirilmadi" };
  }

  if (loading) {
    return (
      <div className="provider-settings">
        <div className="provider-loading">Yukleniyordu...</div>
      </div>
    );
  }

  return (
    <div className="provider-settings">
      <div className="provider-header">
        <h2>LLM Saglayicilar</h2>
        <p className="provider-subtitle">
          Yerel veya bulut tabanli LLM saglayicilarini yapilandirin. Aktif saglayici tum isteklerde kullanilir.
        </p>
      </div>

      <div className="provider-grid">
        {providers.map((p) => {
          const badge = getStatusBadge(p);
          const result = testResults[p.id];
          const isTesting = testing === p.id;
          const isSaving = saving === p.id;
          const unsaved = hasUnsavedChanges(p.id);

          return (
            <div key={p.id} className={`provider-card ${p.is_active ? "active" : ""}`}>
              <div className="provider-card-header">
                <div className="provider-name">{p.name}</div>
                <span className={`provider-badge ${badge.cls}`}>{badge.text}</span>
              </div>

              {p.type !== "ollama" && (
                <div className="provider-field">
                  <label>API Key:</label>
                  <div className="provider-key-row">
                    <input
                      type={showKeys[p.id] ? "text" : "password"}
                      placeholder="API anahtarinizi girin..."
                      value={getEditValue(p.id, "api_key")}
                      onChange={(e) => setEditField(p.id, "api_key", e.target.value)}
                    />
                    <button
                      className="provider-toggle-key"
                      onClick={() =>
                        setShowKeys((prev) => ({ ...prev, [p.id]: !prev[p.id] }))
                      }
                    >
                      {showKeys[p.id] ? "Gizle" : "Goster"}
                    </button>
                  </div>
                </div>
              )}

              <div className="provider-field">
                <label>Base URL:</label>
                <input
                  type="text"
                  value={getEditValue(p.id, "base_url")}
                  onChange={(e) => setEditField(p.id, "base_url", e.target.value)}
                />
              </div>

              <div className="provider-field">
                <label>Model:</label>
                <div className="provider-model-row">
                  <input
                    type="text"
                    value={getEditValue(p.id, "model")}
                    onChange={(e) => setEditField(p.id, "model", e.target.value)}
                    list={`models-${p.id}`}
                  />
                  {p.models && p.models.length > 0 && (
                    <datalist id={`models-${p.id}`}>
                      {p.models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  )}
                </div>
              </div>

              {result && (
                <div className={`provider-test-result ${result.ok ? "success" : "error"}`}>
                  {result.message}
                </div>
              )}

              <div className="provider-card-actions">
                <button
                  className="btn-test"
                  onClick={() => testConnection(p.id)}
                  disabled={isTesting}
                >
                  {isTesting ? "Test Ediliyor..." : "Baglanti Test Et"}
                </button>

                {unsaved && (
                  <button
                    className="btn-save"
                    onClick={() => saveProvider(p.id)}
                    disabled={isSaving}
                  >
                    {isSaving ? "Kaydediliyor..." : "Kaydet"}
                  </button>
                )}

                {!p.is_active && (
                  <button className="btn-activate" onClick={() => setActive(p.id)}>
                    Aktif Yap
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
