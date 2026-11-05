export function estimatedLineCost(rate: number | null | undefined, quantity: number): number | null {
  if (typeof rate !== 'number' || !Number.isFinite(rate) || rate < 0 || !Number.isFinite(quantity) || quantity <= 0) return null;
  const amount = rate * quantity;
  return Number.isFinite(amount) ? amount : null;
}

export function estimatedTotalCost(rows: Array<{ item_code: string; qty: number }>, rates: Record<string, number | null>): number | null {
  if (!rows.length) return null;
  let total = 0;
  for (const row of rows) {
    const amount = estimatedLineCost(rates[row.item_code], row.qty);
    if (amount === null) return null;
    total += amount;
  }
  return Number.isFinite(total) ? total : null;
}
