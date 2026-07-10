import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

export default function Username() {
  const { setUser } = useAuth();
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await api.setUsername(username);
      setUser(user);
    } catch (requestError) {
      setError(requestError.message || "That username isn't available.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="screen login-screen username-screen">
      <section className="login-hero">
        <div className="label">Your public identity</div>
        <h1>Pick your signal.</h1>
        <p>Your username appears on the standings and alongside your market calls.</p>
      </section>
      <section className="login-card">
        <form onSubmit={submit}>
          <label>
            Username
            <input
              className="call-input"
              required
              minLength="3"
              maxLength="32"
              autoCapitalize="none"
              autoComplete="username"
              placeholder="your_name"
              value={username}
              onChange={(event) => setUsername(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
            />
          </label>
          <small className="field-help">3-32 lowercase letters, numbers, or underscores.</small>
          <button className="primary-btn full" disabled={busy || username.length < 3}>
            {busy ? "Saving..." : "Enter Psyblr"}
          </button>
        </form>
        {error && <div className="notice">{error}</div>}
      </section>
    </main>
  );
}
