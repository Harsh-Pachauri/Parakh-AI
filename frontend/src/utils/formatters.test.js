import test from 'node:test'
import assert from 'node:assert'
import {
  formatScoreValue,
  formatScoreOutof,
  formatRatioPercent,
  formatPercentValue,
  formatRubricEntry,
} from './formatters.js'

test('formatScoreValue formats fractional and integer numbers', () => {
  assert.strictEqual(formatScoreValue(7), '7')
  assert.strictEqual(formatScoreValue(7.0), '7')
  assert.strictEqual(formatScoreValue(7.5), '7.5')
  assert.strictEqual(formatScoreValue(1.3333333), '1.3')
  assert.strictEqual(formatScoreValue(0), '0')
})

test('formatScoreValue handles missing or invalid values safely', () => {
  assert.strictEqual(formatScoreValue(null), '—')
  assert.strictEqual(formatScoreValue(undefined), '—')
  assert.strictEqual(formatScoreValue(''), '—')
  assert.strictEqual(formatScoreValue(NaN), '—')
  assert.strictEqual(formatScoreValue('invalid'), '—')
})

test('formatScoreOutof formats scores out of scale', () => {
  assert.strictEqual(formatScoreOutof(2, 10), '2 / 10')
  assert.strictEqual(formatScoreOutof(7.5, 10), '7.5 / 10')
  assert.strictEqual(formatScoreOutof(1.3333333, 10), '1.3 / 10')
  assert.strictEqual(formatScoreOutof(0, 10), '0 / 10')
  assert.strictEqual(formatScoreOutof(null, 10), '—')
  assert.strictEqual(formatScoreOutof(undefined, 10), '—')
})

test('formatRatioPercent converts ratios to clamped percentages', () => {
  assert.strictEqual(formatRatioPercent(0.38), '38%')
  assert.strictEqual(formatRatioPercent(0.13333333), '13%')
  assert.strictEqual(formatRatioPercent(1.0), '100%')
  assert.strictEqual(formatRatioPercent(0), '0%')
  assert.strictEqual(formatRatioPercent(0.0), '0%')
  assert.strictEqual(formatRatioPercent(-0.1), '0%')
  assert.strictEqual(formatRatioPercent(1.5), '100%')
  assert.strictEqual(formatRatioPercent(null), '—')
  assert.strictEqual(formatRatioPercent(undefined), '—')
  assert.strictEqual(formatRatioPercent(NaN), '—')
})

test('formatPercentValue formats integer/direct percentages', () => {
  assert.strictEqual(formatPercentValue(75), '75%')
  assert.strictEqual(formatPercentValue(100), '100%')
  assert.strictEqual(formatPercentValue(0), '0%')
  assert.strictEqual(formatPercentValue(-5), '0%')
  assert.strictEqual(formatPercentValue(120), '100%')
  assert.strictEqual(formatPercentValue(null), '—')
})

test('formatRubricEntry standardizes rubric dimensions and labels', () => {
  // Correctness (0-10 scale)
  const corr = formatRubricEntry('correctness', 2)
  assert.deepStrictEqual(corr, { label: 'Correctness', value: '2 / 10' })

  // Completeness (0-10 scale)
  const comp = formatRubricEntry('completeness', 7.5)
  assert.deepStrictEqual(comp, { label: 'Completeness', value: '7.5 / 10' })

  // Clarity (0-10 scale)
  const clar = formatRubricEntry('clarity', 1)
  assert.deepStrictEqual(clar, { label: 'Clarity', value: '1 / 10' })

  // llm_score (0-1 ratio, normalized to 0-10 scale)
  const llm = formatRubricEntry('llm_score', 0.13333333333333333)
  assert.deepStrictEqual(llm, { label: 'Rubric mean', value: '1.3 / 10' })

  // llm_score higher value
  const llmHigh = formatRubricEntry('llm_score', 0.43333333333333335)
  assert.deepStrictEqual(llmHigh, { label: 'Rubric mean', value: '4.3 / 10' })

  // Non-numeric entries like justification are skipped (returns null)
  assert.strictEqual(formatRubricEntry('justification', 'Some text reason'), null)
  assert.strictEqual(formatRubricEntry('correctness', null), null)
  assert.strictEqual(formatRubricEntry('correctness', undefined), null)
})
