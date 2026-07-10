import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

function today() {
  return new Date().toISOString().slice(0, 10);
}

function parseObjects(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, aliasText = ""] = line.split("|");
      return {
        canonical_name: name.trim(),
        aliases: aliasText.split(",").map((alias) => alias.trim()).filter(Boolean),
      };
    });
}

export default function AdminCreateMarket() {
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({
    prompt: "",
    category_id: "",
    object_type: "",
    closes_in_minutes: "1440",
    source_name: "",
    source_url: "",
    source_updated_at: today(),
    scope_statement: "",
    coverage_statement: "",
    objects_text: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    api.categories().then((data) => {
      setCategories(data);
      setForm((current) => ({ ...current, category_id: current.category_id || data[0]?.id || "" }));
    }).catch(() => setError("Could not load market categories."));
  }, []);

  const objects = useMemo(() => parseObjects(form.objects_text), [form.objects_text]);
  const update = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSuccess(null);
    if (objects.length < 3) {
      setError("Add at least three distinct canonical objects to the answer universe.");
      return;
    }
    setBusy(true);
    try {
      const payload = { ...form };
      delete payload.objects_text;
      const market = await api.createMarket({
        ...payload,
        closes_in_minutes: Number(form.closes_in_minutes),
        objects,
      });
      setSuccess(market);
      setForm((current) => ({
        ...current,
        prompt: "",
        object_type: "",
        scope_statement: "",
        coverage_statement: "",
        objects_text: "",
      }));
    } catch (requestError) {
      setError(requestError.message || "Market creation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="screen stack-screen admin-screen">
      <header className="page-hero">
        <div>
          <div className="label">Administrator</div>
          <h1>Create a market</h1>
          <p>Every market is published with a finite, source-bound answer universe.</p>
        </div>
      </header>

      <section className="panel-section universe-guide">
        <div className="section-heading">
          <span>Publication rule</span>
          <strong>Source + scope + complete object list</strong>
        </div>
        <p>
          The cited source defines what "complete" means. The app validates distinct canonical objects and aliases before publishing, then restricts search to that list.
        </p>
      </section>

      <form className="admin-form" onSubmit={submit}>
        <label>
          Market question
          <textarea required value={form.prompt} onChange={update("prompt")} placeholder="Which album has the strongest opening track?" />
        </label>
        <div className="form-grid">
          <label>
            Category
            <select required value={form.category_id} onChange={update("category_id")}>
              {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
          </label>
          <label>
            Object type
            <input required value={form.object_type} onChange={update("object_type")} placeholder="album" />
          </label>
          <label>
            Closes in (minutes)
            <input required type="number" min="5" max="10080" value={form.closes_in_minutes} onChange={update("closes_in_minutes")} />
          </label>
        </div>

        <div className="source-block">
          <div className="section-heading"><span>Source of record</span><strong>Required</strong></div>
          <label>
            Source name
            <input required value={form.source_name} onChange={update("source_name")} placeholder="Official awards archive" />
          </label>
          <label>
            Source URL
            <input required type="url" value={form.source_url} onChange={update("source_url")} placeholder="https://example.com/source" />
          </label>
          <label>
            Source last updated
            <input required type="date" value={form.source_updated_at} onChange={update("source_updated_at")} />
          </label>
          <label>
            Scope statement
            <textarea required value={form.scope_statement} onChange={update("scope_statement")} placeholder="All eligible albums released in the selected period." />
          </label>
          <label>
            Coverage statement
            <textarea required value={form.coverage_statement} onChange={update("coverage_statement")} placeholder="This list includes every item in the source scope, normalized to one canonical name per object." />
          </label>
        </div>

        <label>
          MECE answer universe
          <textarea
            required
            className="universe-input"
            value={form.objects_text}
            onChange={update("objects_text")}
            placeholder={"Canonical object | alias one, alias two\nAnother canonical object | another alias\nThird canonical object"}
          />
          <small className="field-help">One canonical object per line. Add optional aliases after a <code>|</code>; separate aliases with commas. {objects.length} objects ready.</small>
        </label>

        <button className="primary-btn full" disabled={busy || objects.length < 3}>
          {busy ? "Validating and publishing..." : "Publish market"}
        </button>
      </form>

      {error && <div className="notice">{error}</div>}
      {success && (
        <section className="panel-section success-panel">
          <span>Published</span>
          <strong>{success.prompt}</strong>
          <p>{success.universe.object_count} source-bound objects are now searchable in this market.</p>
        </section>
      )}
    </main>
  );
}
