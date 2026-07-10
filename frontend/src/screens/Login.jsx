import { useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { setUser } = useAuth();
  const googleEnabled = import.meta.env.VITE_GOOGLE_AUTH_ENABLED === "true";
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function emailLogin(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { access_token, user } = await api.emailLogin(email.trim());
      setToken(access_token);
      setUser(user);
    } catch (error) {
      setErr(error.message || "Email sign-in failed. Please try again.");
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
        <form onSubmit={emailLogin}>
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
          <button className="primary-btn full" disabled={busy || !email.trim()}>
            {busy ? "Signing in..." : "Continue with email"}
          </button>
        </form>
        {googleEnabled && (
          <>
            <div className="auth-divider"><span>or</span></div>
            <a className="ghost-btn full" href={`${api.base}/auth/google/login`}>
              Continue with Google
            </a>
          </>
        )}
        {err && <div className="notice">{err}</div>}
      </section>
    </main>
  );
}
