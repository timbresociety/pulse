const PLATFORM_FEE_BPS = 200;
const BPS_TOTAL = 10_000;
const MIN_ACCURACY_MULTIPLIER = Math.exp(-20);

export function platformFeeCents(stakeCents) {
  return Math.floor((Math.max(0, stakeCents) * PLATFORM_FEE_BPS + 5_000) / BPS_TOTAL);
}

export function maximumPayoutCents({
  poolVolumeCents = 0,
  netPoolVolumeCents = 0,
  stakeCents = 0,
} = {}) {
  const safeStake = Math.max(0, Math.round(stakeCents));
  if (!safeStake) return 0;

  const netStake = Math.max(0, safeStake - platformFeeCents(safeStake));
  const crowdNetPool = netPoolVolumeCents > 0
    ? netPoolVolumeCents
    : Math.max(0, Math.round(poolVolumeCents * 0.98));
  const totalNetPool = crowdNetPool + netStake;
  const maximumDenominator = (crowdNetPool * MIN_ACCURACY_MULTIPLIER) + netStake;

  return maximumDenominator > 0
    ? (totalNetPool * netStake) / maximumDenominator
    : 0;
}

export function formatPayout(cents = 0) {
  const safeCents = Math.max(0, Number(cents) || 0);
  if (safeCents > 0 && safeCents < 1) return "<$0.01";

  const dollars = safeCents / 100;
  if (dollars >= 1_000) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(dollars);
  }

  const roundedCents = Math.floor(safeCents);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: roundedCents % 100 ? 2 : 0,
  }).format(roundedCents / 100);
}
