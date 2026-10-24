import test from 'node:test'
import assert from 'node:assert/strict'
import {
  filterRecommendations,
  getTopicStatusBadge,
  formatDimensionSummary,
  buildPracticeUrl,
} from './studentInsightsHelpers.js'

test('filterRecommendations limits items safely', () => {
  assert.deepEqual(filterRecommendations(null), [])
  assert.deepEqual(filterRecommendations(undefined), [])
  assert.equal(filterRecommendations([1, 2, 3, 4, 5], 3).length, 3)
})

test('getTopicStatusBadge assigns accurate badges', () => {
  assert.equal(getTopicStatusBadge('weakness').label, 'Needs Focus')
  assert.equal(getTopicStatusBadge('strength').label, 'Strong Mastery')
  assert.equal(getTopicStatusBadge('developing').label, 'Developing')
  assert.equal(getTopicStatusBadge(null).label, 'Untested')
})

test('formatDimensionSummary formats dimensions accurately', () => {
  assert.equal(formatDimensionSummary(null), 'Evaluation dimensions unavailable')
  assert.equal(
    formatDimensionSummary({ correctness: 8.5, completeness: 7.0, clarity: 9.0 }),
    'Accuracy: 8.5/10 · Completeness: 7.0/10 · Clarity: 9.0/10'
  )
  assert.equal(
    formatDimensionSummary({ correctness: 6.0 }),
    'Accuracy: 6.0/10'
  )
})

test('buildPracticeUrl constructs targeted practice routes', () => {
  assert.equal(buildPracticeUrl(null), '/')
  assert.equal(buildPracticeUrl('c1'), '/viva/c1')
  assert.equal(buildPracticeUrl('c1', 't1'), '/viva/c1?topic=t1')
})
