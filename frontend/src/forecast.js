const TOTAL_PERCENT = 100;
const BPS_PER_PERCENT = 100;

function clampPercent(value) {
  return Math.min(TOTAL_PERCENT, Math.max(0, Math.round(Number(value) || 0)));
}

function distributePercent(points, weights) {
  if (!weights.length) return [];
  if (points <= 0) return weights.map(() => 0);

  const weightTotal = weights.reduce((sum, weight) => sum + Math.max(0, weight), 0);
  if (weightTotal === 0) {
    const base = Math.floor(points / weights.length);
    let remainder = points - (base * weights.length);
    return weights.map(() => {
      const allocation = base + (remainder > 0 ? 1 : 0);
      remainder -= remainder > 0 ? 1 : 0;
      return allocation;
    });
  }

  const quotas = weights.map((weight, index) => {
    const exact = (Math.max(0, weight) * points) / weightTotal;
    return { index, value: Math.floor(exact), fraction: exact - Math.floor(exact) };
  });
  let remainder = points - quotas.reduce((sum, quota) => sum + quota.value, 0);

  [...quotas]
    .sort((left, right) => right.fraction - left.fraction || left.index - right.index)
    .forEach((quota) => {
      if (remainder <= 0) return;
      quotas[quota.index].value += 1;
      remainder -= 1;
    });

  return quotas.map((quota) => quota.value);
}

export function equalAllocations(options) {
  if (!options.length) return {};
  const percents = distributePercent(TOTAL_PERCENT, options.map(() => 1));
  return Object.fromEntries(
    options.map((option, index) => [option.id, percents[index] * BPS_PER_PERCENT]),
  );
}

export function rebalanceAllocations(
  options,
  allocations,
  targetId,
  nextPercent,
  lockedIds = [],
) {
  if (!options.some((option) => option.id === targetId)) return allocations;
  const locked = new Set(lockedIds);
  if (options.length === 1) return { [targetId]: TOTAL_PERCENT * BPS_PER_PERCENT };

  const targetIndex = options.findIndex((option) => option.id === targetId);
  const cyclicOptions = [
    ...options.slice(targetIndex + 1),
    ...options.slice(0, targetIndex),
  ];
  const lockedOptions = options.filter((option) => (
    option.id !== targetId && locked.has(option.id)
  ));
  const lockedPercent = lockedOptions.reduce(
    (sum, option) => sum + ((Number(allocations[option.id]) || 0) / BPS_PER_PERCENT),
    0,
  );
  const adjustableOptions = cyclicOptions.filter((option) => (
    !locked.has(option.id)
  ));
  const availablePercent = Math.max(0, TOTAL_PERCENT - lockedPercent);
  const targetPercent = adjustableOptions.length
    ? Math.min(availablePercent, clampPercent(nextPercent))
    : availablePercent;
  const currentWeights = adjustableOptions.map(
    (option) => Number(allocations[option.id]) || 0,
  );
  const weightRange = currentWeights.length
    ? Math.max(...currentWeights) - Math.min(...currentWeights)
    : 0;
  const otherWeights = weightRange <= BPS_PER_PERCENT
    ? currentWeights.map(() => 1)
    : currentWeights;
  const otherPercents = distributePercent(
    availablePercent - targetPercent,
    otherWeights,
  );

  const next = Object.fromEntries(
    lockedOptions.map((option) => [option.id, Number(allocations[option.id]) || 0]),
  );
  next[targetId] = targetPercent * BPS_PER_PERCENT;
  adjustableOptions.forEach((option, index) => {
    next[option.id] = otherPercents[index] * BPS_PER_PERCENT;
  });
  return next;
}
