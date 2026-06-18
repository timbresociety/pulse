import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function Categories() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [cats, setCats] = useState([]);
  const [selected, setSelected] = useState(new Set((user.categories || []).map((c) => c.id)));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.categories().then(setCats);
  }, []);

  function toggle(id) {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  }

  async function save() {
    setBusy(true);
    const updated = await api.setCategories([...selected]);
    setUser(updated);
    setBusy(false);
    nav("/feed");
  }

  return (
    <div className="screen">
      <div className="brand">Pick your worlds</div>
      <div className="muted" style={{ marginBottom: 16 }}>Choose the categories you want to play.</div>
      <div className="grid">
        {cats.map((c) => {
          const on = selected.has(c.id);
          return (
            <div
              key={c.id}
              className={`cat-card ${on ? "" : "off"}`}
              style={{ background: c.theme?.color || "var(--accent)" }}
              onClick={() => toggle(c.id)}
            >
              {on && <span className="tick">✓</span>}
              {c.name}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 20 }}>
        <button className="btn btn-primary" disabled={busy || selected.size === 0} onClick={save}>
          {selected.size === 0 ? "Select at least one" : `Play ${selected.size} ${selected.size === 1 ? "world" : "worlds"}`}
        </button>
      </div>
    </div>
  );
}
