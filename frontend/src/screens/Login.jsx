import { useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function devLogin(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { access_token } = await api.devLogin(email.trim());
      setToken(access_token);
      await refresh();
    } catch {
      setErr("Dev login failed. Check that DEBUG=true on the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="screen login-screen">
      <section className="login-hero">
        <div className="psyblr-wordmark hero-wordmark" aria-label="Psyblr">
          <span className="chrome-text">Psy</span><span className="accent-word">blr</span>
        </div>
        <div className="label">Culture markets</div>
        <h1>Make your call. Read the room.</h1>
        <p>Choose a canonical answer, lock your call, and see where the market lands.</p>
      </section>

      <section className="login-card">
        <a className="primary-btn full" href={`${api.base}/auth/google/login`}>
          Continue with Google
        </a>

        <div className="auth-divider"><span>or</span></div>

        <form onSubmit={devLogin}>
          <label>
            Email address
            <input
              className="call-input"
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button className="ghost-btn full" disabled={busy || !email.trim()}>
            {busy ? "Signing in..." : "Dev login"}
          </button>
        </form>
        {err && <div className="notice">{err}</div>}
      </section>
    </main>
  );
}
