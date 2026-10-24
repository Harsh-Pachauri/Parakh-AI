import test from 'node:test'
import assert from 'node:assert/strict'
import {
  formatReportScore,
  getPerformanceTier,
  serializeReportParams,
  filterReportItems,
  validateDateRange,
} from './reportHelpers.js'

test('formatReportScore handles null, undefined, invalid, and standard scores', () => {
  assert.equal(formatReportScore(null), '—')
  assert.equal(formatReportScore(undefined), '—')
  assert.equal(formatReportScore('abc'), '—')
  assert.equal(formatReportScore(0.854), '85%')
  assert.equal(formatReportScore(1.0), '100%')
  assert.equal(formatReportScore(0.0), '0%')
})

test('getPerformanceTier classifies scores into correct tiers', () => {
  assert.equal(getPerformanceTier(0.85).label, 'Mastery (80%+)')
  assert.equal(getPerformanceTier(0.72).label, 'Proficient (65-79%)')
  assert.equal(getPerformanceTier(0.55).label, 'Developing (50-64%)')
  assert.equal(getPerformanceTier(0.40).label, 'Needs Attention (<50%)')
  assert.equal(getPerformanceTier(null).label, 'Unscored')
})

test('serializeReportParams generates query strings cleanly omitting empty keys', () => {
  const params = {
    course_id: 'c-101',
    topic_id: '',
    status: 'all',
    from_date: '2026-10-01',
  }
  const qs = serializeReportParams(params)
  assert.ok(qs.includes('course_id=c-101'))
  assert.ok(qs.includes('from_date=2026-10-01'))
  assert.ok(!qs.includes('topic_id'))
  assert.ok(!qs.includes('status=all'))
})

test('filterReportItems filters by search and type', () => {
  const items = [
    { title: 'Midterm Viva', course_name: 'Algorithms', type: 'assignment' },
    { title: 'Practice Viva', course_name: 'Networks', type: 'practice' },
    { title: 'Database Quiz', course_name: 'Databases', type: 'custom_assessment' },
  ]
  assert.equal(filterReportItems(items, 'algorithms', 'all').length, 1)
  assert.equal(filterReportItems(items, '', 'practice').length, 1)
  assert.equal(filterReportItems(items, '', 'all').length, 3)
})

test('validateDateRange validates chronologically valid date ranges', () => {
  assert.equal(validateDateRange('2026-10-01', '2026-10-20').valid, true)
  assert.equal(validateDateRange('', '2026-10-20').valid, true)
  const invalid = validateDateRange('2026-10-25', '2026-10-10')
  assert.equal(invalid.valid, false)
  assert.ok(invalid.error)
})
