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
              className={`channel-card${on ? " selected" : ""}`}
              style={{ "--channel": category.theme?.color || "#90d6ff" }}
              aria-pressed={on}
              aria-label={`${category.name}: ${on ? "in your feed; tap to remove" : "not in your feed; tap to add"}`}
              onClick={() => toggle(category.id)}
            >
              <span className="channel-card__inner">
                <span className="channel-card__face channel-card__front">
                  <span className="channel-card__name">{category.name}</span>
                  <small>Tap to add</small>
                </span>
                <span className="channel-card__face channel-card__back">
                  <span className="channel-card__title">
                    <span className="channel-card__check" aria-hidden="true">✓</span>
                    <span className="channel-card__name">{category.name}</span>
                  </span>
                  <small>In feed</small>
                </span>
              </span>
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
