import assert from "node:assert/strict";
import test from "node:test";

import { breakEvenAccuracy, hasFieldBenchmarks } from "./revealMath.js";

test("uses populated field benchmarks and rejects empty placeholder values", () => {
  assert.equal(hasFieldBenchmarks({
    crowd_median_accuracy_score: 61.4,
    crowd_top_quartile_accuracy_score: 74.2,
    crowd_top_ten_accuracy_score: 86.1,
  }), true);
  assert.equal(hasFieldBenchmarks({
    crowd_median_accuracy_score: 0,
    crowd_top_quartile_accuracy_score: 0,
    crowd_top_ten_accuracy_score: 0,
  }), false);
});

test("uses a supplied break-even score when the reveal payload includes one", () => {
  assert.equal(breakEvenAccuracy({ break_even_accuracy_score: 68.5 }), 68.5);
});

test("derives a non-zero break-even score for saved reveal payloads", () => {
  const score = breakEvenAccuracy({
    stake_cents: 50_000,
    user_fee_cents: 1_000,
    accuracy_score: 33.2,
    net_pool_cents: 12_347_997,
    payout_cents: 22_707,
  });

  assert.ok(score > 33.2);
  assert.ok(score < 100);
});

test("does not invent a break-even score without enough settlement data", () => {
  assert.equal(breakEvenAccuracy({
    stake_cents: 50_000,
    accuracy_score: 33.2,
    payout_cents: 0,
  }), null);
});
