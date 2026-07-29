import { useEffect, useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { setUser } = useAuth();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [devCode, setDevCode] = useState("");
  const [methods, setMethods] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.authMethods()
      .then(setMethods)
      .catch(() => setMethods({
        email_otp: false,
        email_login: true,
        google: import.meta.env.VITE_GOOGLE_AUTH_ENABLED === "true",
      }));
  }, []);

  function finishLogin({ access_token, user }) {
    setToken(access_token);
    setUser(user);
  }

  async function startEmailLogin(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      if (methods?.email_otp) {
        const response = await api.requestEmailOtp(email.trim());
        setChallengeId(response.challenge_id);
        setDevCode(response.dev_code || "");
      } else if (methods?.email_login !== false) {
        finishLogin(await api.emailLogin(email.trim()));
      } else {
        throw new Error("Email sign-in is temporarily unavailable.");
      }
    } catch (error) {
      setErr(error.message || "Email sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event) {
    event.preventDefault();
    setBusy(true);
    setErr("");
    try {
      finishLogin(await api.verifyEmailOtp(challengeId, code));
    } catch (error) {
      setErr(error.message || "Code verification failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function changeEmail() {
    setChallengeId("");
    setCode("");
    setDevCode("");
    setErr("");
  }

  return (
    <main className="screen login-screen">
      <section className="login-hero">
        <div className="pulse-wordmark hero-wordmark" aria-label="Pulse">
          Pulse<span>.</span>
        </div>
        <div className="label">Crowd-reading game</div>
        <h1>Vote what you think. Predict everyone else.</h1>
        <p>Read a simulated crowd, stake test credits, and reveal how close your forecast was.</p>
      </section>

      <section className="login-card">
        {!challengeId ? (
          <form onSubmit={startEmailLogin}>
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
            <button className="primary-btn full" disabled={busy || !email.trim() || methods === null}>
              {busy ? "Sending..." : methods?.email_otp ? "Email me a code" : "Continue with email"}
            </button>
          </form>
        ) : (
          <form onSubmit={verifyCode}>
            <label>
              6-digit code sent to {email}
              <input
                className="call-input otp-input"
                type="text"
                required
                autoFocus
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength="6"
                placeholder="000000"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              />
            </label>
            <button className="primary-btn full" disabled={busy || code.length !== 6}>
              {busy ? "Checking..." : "Verify and sign in"}
            </button>
            <button className="text-btn full" type="button" onClick={changeEmail} disabled={busy}>
              Use a different email
            </button>
          </form>
        )}
        {(methods?.google ?? import.meta.env.VITE_GOOGLE_AUTH_ENABLED === "true") && (
          <>
            <div className="auth-divider"><span>or</span></div>
            <a className="ghost-btn full" href={`${api.base}/auth/google/login`}>
              Continue with Google
            </a>
          </>
        )}
        {devCode && <div className="notice">Development code: {devCode}</div>}
        {err && <div className="notice">{err}</div>}
      </section>
    </main>
  );
}
