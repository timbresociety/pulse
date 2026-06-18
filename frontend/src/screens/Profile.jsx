import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Profile() {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <div className="screen">
      <div className="brand" style={{ marginBottom: 16 }}>Profile</div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 800, fontSize: 20 }}>{user.display_name || user.email}</div>
        <div className="muted">{user.email}</div>
        <div className="stats" style={{ marginTop: 14 }}>
          <span className="pill">🪙 {user.coins} coins</span>
          <span className="pill">⚡ {user.pulse_score} pulse</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>Your worlds</div>
        <div>
          {(user.categories || []).map((c) => (
            <span key={c.id} className="cat-pill" style={{ background: c.theme?.color || "var(--accent)", marginRight: 6, marginBottom: 6, display: "inline-block" }}>
              {c.name}
            </span>
          ))}
        </div>
        <button className="btn btn-ghost" style={{ marginTop: 14 }} onClick={() => nav("/categories")}>
          Edit worlds
        </button>
      </div>

      <button className="btn btn-ghost" onClick={logout}>Log out</button>
    </div>
  );
}
