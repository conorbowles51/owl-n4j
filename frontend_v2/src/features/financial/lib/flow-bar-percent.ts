// Only the bounded 0–100 bar width becomes a Number; money stays exact BigInt.
export function flowBarPercent(amount: string, maximum: bigint) {
  return maximum === 0n ? 0 : Number((BigInt(amount) * 10000n) / maximum) / 100
}
