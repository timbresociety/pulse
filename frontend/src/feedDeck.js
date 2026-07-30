function closingSeconds(market) {
  const value = Number(market?.reveal_seconds);
  return Number.isFinite(value) ? Math.max(0, value) : Number.MAX_SAFE_INTEGER;
}
export function orderMarketsForDeck(markets = []) {
  const categoryOrder = new Map();
  const categoryOccurrence = new Map();

  return markets
    .map((market, inputIndex) => {
      const categoryKey = market.category?.slug || market.category?.id || "other";
      if (!categoryOrder.has(categoryKey)) categoryOrder.set(categoryKey, categoryOrder.size);
      const occurrence = categoryOccurrence.get(categoryKey) || 0;
      categoryOccurrence.set(categoryKey, occurrence + 1);
      return {
        market,
        inputIndex,
        occurrence,
        categoryIndex: categoryOrder.get(categoryKey),
      };
    })
    .sort((left, right) => (
      closingSeconds(left.market) - closingSeconds(right.market)
      || left.occurrence - right.occurrence
      || left.categoryIndex - right.categoryIndex
      || left.inputIndex - right.inputIndex
    ))
    .map(({ market }) => market);
}
