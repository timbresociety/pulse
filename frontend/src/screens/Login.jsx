import { useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState("email");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function sendEmail(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.startEmailLogin(email.trim());
      setStage("code");
    } catch (error) {
      setErr(error.message || "We couldn't send that sign-in email.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { access_token } = await api.verifyEmailLogin(email.trim(), code.trim());
      setToken(access_token);
      await refresh();
    } catch (error) {
      setErr(error.message || "That code didn't work. Try again.");
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

        {stage === "email" ? (
          <form onSubmit={sendEmail}>
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
              {busy ? "Sending..." : "Email me a sign-in code"}
            </button>
          </form>
        ) : (
          <form onSubmit={verifyCode}>
            <div className="auth-note">
              <strong>Check your inbox</strong>
              <span>We sent a six-digit code and a one-use sign-in link to {email}.</span>
            </div>
            <label>
              One-time code
              <input
                className="call-input code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength="6"
                placeholder="000000"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              />
            </label>
            <button className="primary-btn full" disabled={busy || code.length !== 6}>
              {busy ? "Verifying..." : "Continue"}
            </button>
            <button className="text-btn" type="button" disabled={busy} onClick={() => setStage("email")}>
              Use a different email
            </button>
          </form>
        )}
        {err && <div className="notice">{err}</div>}
      </section>
    </main>
  );
}
