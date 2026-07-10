import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function formatNumber(value = 0) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export default function Wallet() {
  const { user } = useAuth();
  const [history, setHistory] = useState([]);

  useEffect(() => {
    api.history(100).then(setHistory).catch(() => setHistory([]));
  }, []);

  const ledger = useMemo(() => {
    const spent = history.reduce((sum, row) => sum + (row.entry_cost || 10), 0);
    const won = history.reduce((sum, row) => sum + (row.coins_won || 0), 0);
    return { spent, won, net: won - spent };
  }, [history]);

  return (
    <main className="screen stack-screen">
      <header className="page-hero wallet-hero">
        <div>
          <div className="label">Wallet</div>
          <h1>{formatNumber(user.coins)} coins</h1>
          <p>Coins buy play. Status has to be earned.</p>
        </div>
        <div className="wallet-stack" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </header>

      <section className="wallet-rule">
        <div>
          <span>Daily free balance</span>
          <strong>100 coins</strong>
        </div>
        <div>
          <span>Market entry</span>
          <strong>10 coins</strong>
        </div>
        <div>
          <span>Ranked calls left</span>
          <strong>{user.ranked_calls_remaining ?? 10}</strong>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-heading">
          <span>Economy rule</span>
          <strong>You can buy more play. You cannot buy status.</strong>
        </div>
        <p>
          Ranked score comes from reading the crowd, early calls, streaks, and category performance.
          Extra casual play can win coins, but status comes from your reads.
        </p>
      </section>

      <section className="metric-band">
        <div>
          <span>Spent</span>
          <strong>{formatNumber(ledger.spent)}</strong>
        </div>
        <div>
          <span>Won</span>
          <strong>{formatNumber(ledger.won)}</strong>
        </div>
        <div>
          <span>Net</span>
          <strong>{ledger.net >= 0 ? "+" : ""}{formatNumber(ledger.net)}</strong>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-heading">
          <span>Top-ups</span>
          <strong>Not live yet</strong>
        </div>
        <p>Free play first. Paid loops later.</p>
      </section>
    </main>
  );
}
