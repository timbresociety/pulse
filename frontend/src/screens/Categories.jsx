import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function Categories() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [cats, setCats] = useState([]);
  const [selected, setSelected] = useState(new Set((user.categories || []).map((category) => category.id)));
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
    <main className="screen stack-screen">
      <header className="page-hero">
        <div>
          <div className="label">Channels</div>
          <h1>Pick channels.</h1>
        </div>
        <div className="hero-stat">
          <strong>{selected.size}</strong>
          <span>active</span>
        </div>
      </header>

      <section className="panel-section">
        <p>
          Pick the rooms Psyblr should pull into your market feed.
        </p>
      </section>

      <section className="channel-grid">
        {cats.map((category) => {
          const on = selected.has(category.id);
          return (
            <button
              key={category.id}
              className={on ? "selected" : ""}
              style={{ "--channel": category.theme?.color || "#90d6ff" }}
              onClick={() => toggle(category.id)}
            >
              <span>{category.name}</span>
              <small>{on ? "In feed" : "Tap to add"}</small>
            </button>
          );
        })}
      </section>

      <button className="primary-btn full" disabled={busy || selected.size === 0} onClick={save}>
        {selected.size === 0 ? "Select at least one channel" : `Enter ${selected.size} channels`}
      </button>
    </main>
  );
}
