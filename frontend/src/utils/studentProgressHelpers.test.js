import test from 'node:test'
import assert from 'node:assert/strict'
import {
  calculateStudentStats,
  filterStudentSessions,
  formatSessionDate,
  getRecentScoreTrend,
} from './studentProgressHelpers.js'

test('calculateStudentStats handles null, undefined, and empty arrays safely', () => {
  const emptyDefaults = {
    totalAttempted: 0,
    completedCount: 0,
    inProgressCount: 0,
    scoredCount: 0,
    averageScore: null,
    averageScorePercent: '—',
    averageScoreRatio: 0,
  }

  assert.deepEqual(calculateStudentStats(null), emptyDefaults)
  assert.deepEqual(calculateStudentStats(undefined), emptyDefaults)
  assert.deepEqual(calculateStudentStats([]), emptyDefaults)
})

test('calculateStudentStats handles in-progress sessions without completed scores', () => {
  const sessions = [
    { id: '1', status: 'in_progress', total_score: null },
    { id: '2', status: 'pending', total_score: null },
  ]

  const stats = calculateStudentStats(sessions)
  assert.equal(stats.totalAttempted, 2)
  assert.equal(stats.completedCount, 0)
  assert.equal(stats.inProgressCount, 2)
  assert.equal(stats.scoredCount, 0)
  assert.equal(stats.averageScore, null)
  assert.equal(stats.averageScorePercent, '—')
  assert.equal(stats.averageScoreRatio, 0)
})

test('calculateStudentStats correctly calculates average score and percentages for completed sessions', () => {
  const sessions = [
    { id: '1', status: 'completed', total_score: 0.8 },
    { id: '2', status: 'completed', total_score: 0.9 },
    { id: '3', status: 'in_progress', total_score: null },
  ]

  const stats = calculateStudentStats(sessions)
  assert.equal(stats.totalAttempted, 3)
  assert.equal(stats.completedCount, 2)
  assert.equal(stats.inProgressCount, 1)
  assert.equal(stats.scoredCount, 2)
  assert.equal(stats.averageScore, 0.85)
  assert.equal(stats.averageScorePercent, '85%')
  assert.equal(stats.averageScoreRatio, 0.85)
})

test('calculateStudentStats handles 0 score without treating it as missing', () => {
  const sessions = [
    { id: '1', status: 'completed', total_score: 0.0 },
  ]

  const stats = calculateStudentStats(sessions)
  assert.equal(stats.totalAttempted, 1)
  assert.equal(stats.completedCount, 1)
  assert.equal(stats.scoredCount, 1)
  assert.equal(stats.averageScore, 0)
  assert.equal(stats.averageScorePercent, '0%')
})

test('filterStudentSessions filters by lifecycle status', () => {
  const sessions = [
    { id: '1', status: 'completed' },
    { id: '2', status: 'in_progress' },
    { id: '3', status: 'completed' },
    { id: '4', status: 'aborted' },
  ]

  assert.equal(filterStudentSessions(null).length, 0)
  assert.equal(filterStudentSessions(sessions, 'all').length, 4)
  assert.deepEqual(
    filterStudentSessions(sessions, 'completed').map((s) => s.id),
    ['1', '3']
  )
  assert.deepEqual(
    filterStudentSessions(sessions, 'in_progress').map((s) => s.id),
    ['2', '4']
  )
})

test('formatSessionDate safely formats dates and fallbacks', () => {
  assert.equal(formatSessionDate(null), '—')
  assert.equal(formatSessionDate(undefined), '—')
  assert.equal(formatSessionDate('invalid-date'), '—')

  const formatted = formatSessionDate('2026-10-23T12:00:00Z')
  assert.ok(formatted.includes('2026'), 'Date should include year 2026')
})

test('getRecentScoreTrend extracts scored completed sessions up to limit', () => {
  const sessions = [
    { id: 's1', status: 'completed', total_score: 0.75, course_name: 'Operating Systems', finished_at: '2026-10-23T10:00:00Z' },
    { id: 's2', status: 'in_progress', total_score: null, course_name: 'Database Systems' },
    { id: 's3', status: 'completed', total_score: 0.85, course_code: 'CS201', finished_at: '2026-10-22T10:00:00Z' },
    { id: 's4', status: 'completed', total_score: null, course_name: 'AI' },
  ]

  const trend = getRecentScoreTrend(sessions, 5)
  assert.equal(trend.length, 2)
  assert.equal(trend[0].courseName, 'Operating Systems')
  assert.equal(trend[0].scorePercent, '75%')
  assert.equal(trend[0].ratio, 0.75)
  assert.equal(trend[1].courseName, 'CS201')
  assert.equal(trend[1].scorePercent, '85%')
})
