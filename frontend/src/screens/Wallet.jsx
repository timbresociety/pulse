import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function money(cents = 0, signed = false) {
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(Math.abs(cents) / 100);
  return signed ? `${cents >= 0 ? "+" : "−"}${formatted}` : formatted;
}

export default function Wallet() {
  const { user, setUser, dataVersion } = useAuth();
  const [wallet, setWallet] = useState(() => api.peek("wallet"));
  const [loading, setLoading] = useState(() => !api.peek("wallet"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      setWallet(await api.wallet());
    } catch (event) {
      setError(event.message || "Could not load wallet.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [dataVersion]);

  async function addCredits() {
    setBusy(true);
    setError("");
    try {
      const updated = await api.addTestCredits();
      setUser((current) => ({ ...current, balance_cents: updated.balance_cents }));
      setWallet((current) => current
        ? { ...current, available_balance_cents: updated.balance_cents }
        : current);
      void load();
    } catch (event) {
      setError(event.message || "Test credits are available only in debug mode.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="screen stack-screen wallet-screen" aria-busy={loading}>
      <header className="wallet-balance-card">
        <div className="label">Test-credit wallet</div>
        <span>Available balance</span>
        <h1>{money(wallet?.available_balance_cents ?? user.balance_cents)}</h1>
        <p>Prototype USD credits · no deposits, withdrawals, or real value.</p>
      </header>

      {error && <div className="notice">{error}</div>}

      <section className="wallet-metrics">
        <div><span>Stakes</span><strong>{wallet ? money(wallet.total_stakes_cents) : "—"}</strong></div>
        <div><span>Payouts</span><strong>{wallet ? money(wallet.total_payouts_cents) : "—"}</strong></div>
        <div><span>Net PnL</span><strong className={wallet ? (wallet.net_pnl_cents >= 0 ? "positive" : "negative") : ""}>{wallet ? money(wallet.net_pnl_cents, true) : "—"}</strong></div>
      </section>

      {wallet?.debug_topup_enabled && (
        <section className="prototype-action">
          <div><span>DEBUG · prototype action</span><strong>Add a fresh testing balance</strong></div>
          <button className="primary-btn" disabled={busy} onClick={addCredits}>{busy ? "Adding…" : "Add $10,000 test credits"}</button>
        </section>
      )}

      <section className="transaction-section">
        <div className="section-heading"><span>Transaction history</span><strong>{wallet ? `${wallet.transactions.length} entries` : "Loading…"}</strong></div>
        <div className="transaction-list">
          {wallet?.transactions?.map((transaction) => (
            <article key={transaction.id}>
              <i className={transaction.amount_cents >= 0 ? "credit" : "debit"}>{transaction.amount_cents >= 0 ? "+" : "−"}</i>
              <div>
                <strong>{transaction.transaction_type === "stake" ? "Market stake" : transaction.transaction_type === "payout" ? "Market payout" : "Test credits"}</strong>
                <span>{transaction.question || "Prototype wallet"}</span>
                <small>{new Date(transaction.created_at).toLocaleString()}</small>
              </div>
              <div className="transaction-amount">
                <strong>{money(transaction.amount_cents, true)}</strong>
                <small>{money(transaction.balance_after_cents)} balance</small>
              </div>
            </article>
          ))}
          {loading && !wallet && <p className="section-empty">Loading transactions…</p>}
          {wallet && !wallet.transactions.length && <p className="section-empty">No transactions yet.</p>}
        </div>
      </section>
    </main>
  );
}
