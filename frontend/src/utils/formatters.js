/**
 * Safe score and percentage formatters for viva examination reports.
 */

/**
 * Format a number to 1 decimal place if fractional, or integer if whole.
 * Handles null/undefined/NaN by returning fallback (default "—").
 */
export function formatScoreValue(val, fallback = '—') {
  if (val === null || val === undefined || val === '') return fallback
  const num = Number(val)
  if (Number.isNaN(num)) return fallback
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}

/**
 * Format a score out of a max scale, e.g. "7 / 10" or "1.3 / 10".
 */
export function formatScoreOutof(val, max = 10, fallback = '—') {
  const formatted = formatScoreValue(val, null)
  if (formatted === null) return fallback
  return `${formatted} / ${max}`
}

/**
 * Format a 0.0 to 1.0 ratio as a rounded percentage, e.g. 0.38 -> "38%".
 * Clamps output between 0% and 100%. Handles null/undefined/NaN safely.
 */
export function formatRatioPercent(ratio, fallback = '—') {
  if (ratio === null || ratio === undefined || ratio === '') return fallback
  const num = Number(ratio)
  if (Number.isNaN(num)) return fallback
  const pct = Math.round(num * 100)
  const clamped = Math.max(0, Math.min(100, pct))
  return `${clamped}%`
}

/**
 * Format an already 0 to 100 percentage value as an integer percentage, e.g. 75 -> "75%".
 * Clamps output between 0% and 100%. Handles null/undefined/NaN safely.
 */
export function formatPercentValue(val, fallback = '—') {
  if (val === null || val === undefined || val === '') return fallback
  const num = Number(val)
  if (Number.isNaN(num)) return fallback
  const clamped = Math.max(0, Math.min(100, Math.round(num)))
  return `${clamped}%`
}

/**
 * Standardize rubric dimension labels and scales.
 * - correctness, completeness, clarity are 0-10 scale.
 * - llm_score is 0-1 scale; normalized to 0-10 scale as "Rubric mean: X.X / 10".
 */
export function formatRubricEntry(key, val) {
  if (val === null || val === undefined || typeof val !== 'number' || Number.isNaN(val)) {
    return null
  }

  switch (key) {
    case 'correctness':
      return { label: 'Correctness', value: formatScoreOutof(val, 10) }
    case 'completeness':
      return { label: 'Completeness', value: formatScoreOutof(val, 10) }
    case 'clarity':
      return { label: 'Clarity', value: formatScoreOutof(val, 10) }
    case 'llm_score':
      return { label: 'Rubric mean', value: formatScoreOutof(val * 10, 10) }
    case 'embedding_score':
      return { label: 'Semantic match', value: formatRatioPercent(val) }
    default:
      return { label: key.replace(/_/g, ' '), value: formatScoreValue(val) }
  }
}
