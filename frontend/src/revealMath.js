export function numeric(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function hasFieldBenchmarks(data) {
  return [
    data.crowd_median_accuracy_score,
    data.crowd_top_quartile_accuracy_score,
    data.crowd_top_ten_accuracy_score,
  ].every((value) => {
    const parsed = numeric(value);
    return parsed !== null && parsed > 0;
  });
}

export function breakEvenAccuracy(data) {
  const provided = numeric(data.break_even_accuracy_score);
  if (provided !== null && provided > 0) return provided;

  const pool = numeric(data.net_pool_cents);
  const payout = numeric(data.payout_cents);
  const stake = numeric(data.stake_cents);
  const score = numeric(data.accuracy_score);
  const hiddenDeduction = numeric(data.user_fee_cents) || 0;
  if (!pool || !payout || !stake || score === null) return null;

  const adjustedStake = stake - hiddenDeduction;
  const payoutShare = payout / pool;
  if (adjustedStake <= 0 || payoutShare <= 0 || payoutShare >= 1 || pool <= stake) return null;

  const currentWeight = adjustedStake * (score / 100);
  const otherWeight = currentWeight * (1 - payoutShare) / payoutShare;
  return (stake * otherWeight / (adjustedStake * (pool - stake))) * 100;
}
