import test from 'node:test'
import assert from 'node:assert/strict'
import {
  filterStudents,
  filterSessionsByDateRange,
  calculateScoreDistribution,
  getStudentScoreProgress,
} from './teacherAnalyticsHelpers.js'

test('filterStudents filters by full name or email case-insensitively', () => {
  const students = [
    { student_id: '1', student_name: 'Alice Johnson', student_email: 'alice@college.edu' },
    { student_id: '2', student_name: 'Bob Smith', student_email: 'bob@college.edu' },
    { student_id: '3', student_name: 'Charlie Brown', student_email: 'charlie@other.edu' },
  ]

  assert.equal(filterStudents(null).length, 0)
  assert.equal(filterStudents(students, '').length, 3)
  assert.equal(filterStudents(students, 'alice').length, 1)
  assert.equal(filterStudents(students, 'ALICE').length, 1)
  assert.equal(filterStudents(students, 'other.edu').length, 1)
  assert.equal(filterStudents(students, 'nonexistent').length, 0)
})

test('filterSessionsByDateRange filters sessions based on relative cutoff', () => {
  const now = new Date('2026-10-23T12:00:00Z').getTime()
  const sessions = [
    { id: 'recent', created_at: '2026-10-22T10:00:00Z' }, // 1 day ago
    { id: 'medium', created_at: '2026-10-10T10:00:00Z' }, // 13 days ago
    { id: 'old', created_at: '2026-09-01T10:00:00Z' },    // > 30 days ago
  ]

  assert.equal(filterSessionsByDateRange(null, '7d', now).length, 0)
  assert.equal(filterSessionsByDateRange(sessions, 'all', now).length, 3)
  assert.deepEqual(
    filterSessionsByDateRange(sessions, '7d', now).map((s) => s.id),
    ['recent']
  )
  assert.deepEqual(
    filterSessionsByDateRange(sessions, '30d', now).map((s) => s.id),
    ['recent', 'medium']
  )
})

test('calculateScoreDistribution partitions scores into accurate tiers', () => {
  const sessions = [
    { status: 'completed', total_score: 0.40 }, // needsAttention
    { status: 'completed', total_score: 0.60 }, // developing
    { status: 'completed', total_score: 0.75 }, // proficient
    { status: 'completed', total_score: 0.90 }, // mastery
    { status: 'in_progress', total_score: null }, // ignored
    { status: 'completed', total_score: null },  // ignored
  ]

  const dist = calculateScoreDistribution(sessions)
  assert.equal(dist.totalScored, 4)
  assert.equal(dist.needsAttention, 1)
  assert.equal(dist.developing, 1)
  assert.equal(dist.proficient, 1)
  assert.equal(dist.mastery, 1)
})

test('getStudentScoreProgress handles insufficient data safely', () => {
  assert.equal(getStudentScoreProgress(null).hasTrend, false)
  assert.equal(getStudentScoreProgress([]).hasTrend, false)

  const singleSession = [{ status: 'completed', total_score: 0.85, created_at: '2026-10-20T10:00:00Z' }]
  const res = getStudentScoreProgress(singleSession)
  assert.equal(res.hasTrend, false)
  assert.equal(res.progress.length, 1)
  assert.equal(res.delta, null)
})

test('getStudentScoreProgress calculates trend and delta when sufficient real data exists', () => {
  const sessions = [
    { id: 's2', status: 'completed', total_score: 0.90, created_at: '2026-10-22T10:00:00Z' },
    { id: 's1', status: 'completed', total_score: 0.75, created_at: '2026-10-18T10:00:00Z' },
  ]

  const res = getStudentScoreProgress(sessions)
  assert.equal(res.hasTrend, true)
  assert.equal(res.progress.length, 2)
  // Chronological order: s1 (0.75) first, then s2 (0.90)
  assert.equal(res.progress[0].id, 's1')
  assert.equal(res.progress[1].id, 's2')
  assert.equal(res.delta, 0.15)
  assert.equal(res.deltaPercent, '+15%')
  assert.equal(res.direction, 'up')
})
