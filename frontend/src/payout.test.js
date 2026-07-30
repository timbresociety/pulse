import assert from "node:assert/strict";
import test from "node:test";
import { formatPayout, maximumPayoutCents, platformFeeCents } from "./payout.js";

test("payout preview uses the same two-percent fee rounding as settlement", () => {
  assert.equal(platformFeeCents(10_000), 200);
  assert.equal(platformFeeCents(333), 7);
});

test("maximum payout stays within the distributable pool", () => {
  const maximum = maximumPayoutCents({
    poolVolumeCents: 2_000_000,
    netPoolVolumeCents: 1_960_000,
    stakeCents: 10_000,
  });

  assert.ok(maximum > 0);
  assert.ok(maximum <= 1_969_800);
});

test("payout formatting keeps large values compact", () => {
  assert.equal(formatPayout(1_240_000), "$12.4K");
  assert.equal(formatPayout(125_000_000), "$1.3M");
});
