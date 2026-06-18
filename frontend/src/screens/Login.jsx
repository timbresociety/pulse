import { useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function devLogin(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { access_token } = await api.devLogin(email.trim());
      setToken(access_token);
      await refresh();
    } catch (e) {
      setErr("Dev login failed (is DEBUG=true on the backend?)");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen center" style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 24 }}>
      <div>
        <div className="brand" style={{ fontSize: 40 }}>Pulse</div>
        <div className="muted">How well can you read culture?</div>
      </div>

      <a className="btn btn-primary" href={`${api.base}/auth/google/login`} style={{ textDecoration: "none", display: "block" }}>
        Continue with Google
      </a>

      <div className="muted">— or, for local testing —</div>

      <form onSubmit={devLogin} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input
          className="input"
          type="email"
          required
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button className="btn btn-ghost" disabled={busy || !email}>Dev login</button>
        {err && <div style={{ color: "var(--lose)", fontSize: 13 }}>{err}</div>}
      </form>
    </div>
  );
}
