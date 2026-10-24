import test from 'node:test'
import assert from 'node:assert/strict'
import {
  validateAssignmentForm,
  formatAssignmentStatus,
  formatAssignmentDate,
  filterAssignments,
  getAssignmentSummaryStats,
} from './assignmentHelpers.js'

test('validateAssignmentForm returns valid for correct payload', () => {
  const form = {
    title: 'Midterm Assessment Assignment',
    course_id: 'c-123',
    assessment_id: 'a-456',
    attempt_limit: 2,
    start_date: '2026-10-24T10:00:00Z',
    deadline: '2026-10-28T10:00:00Z',
  }

  const result = validateAssignmentForm(form)
  assert.equal(result.valid, true)
  assert.deepEqual(result.errors, {})
})

test('validateAssignmentForm catches missing title, course, assessment, and invalid attempts', () => {
  const form = {
    title: '   ',
    course_id: '',
    assessment_id: '',
    attempt_limit: 0,
  }

  const result = validateAssignmentForm(form)
  assert.equal(result.valid, false)
  assert.ok(result.errors.title)
  assert.ok(result.errors.course_id)
  assert.ok(result.errors.assessment_id)
  assert.ok(result.errors.attempt_limit)
})

test('validateAssignmentForm validates that deadline is after start_date', () => {
  const form = {
    title: 'Valid Title',
    course_id: 'c-1',
    assessment_id: 'a-1',
    attempt_limit: 1,
    start_date: '2026-10-25T10:00:00Z',
    deadline: '2026-10-24T10:00:00Z',
  }

  const result = validateAssignmentForm(form)
  assert.equal(result.valid, false)
  assert.equal(
    result.errors.deadline,
    'Deadline must be later than the scheduled start date.'
  )
})

test('formatAssignmentStatus returns expected labels and css classes', () => {
  assert.deepEqual(formatAssignmentStatus('active'), {
    label: 'Active',
    className: 'status-tag published',
  })
  assert.deepEqual(formatAssignmentStatus('available'), {
    label: 'Available Now',
    className: 'status-tag published',
  })
  assert.deepEqual(formatAssignmentStatus('scheduled'), {
    label: 'Scheduled',
    className: 'status-tag info',
  })
  assert.deepEqual(formatAssignmentStatus('submitted'), {
    label: 'Submitted',
    className: 'status-tag submitted',
  })
  assert.deepEqual(formatAssignmentStatus('overdue'), {
    label: 'Overdue',
    className: 'status-tag danger',
  })
  assert.deepEqual(formatAssignmentStatus('closed'), {
    label: 'Closed',
    className: 'status-tag draft',
  })
})

test('formatAssignmentDate handles null and valid ISO dates', () => {
  assert.equal(formatAssignmentDate(null), 'No date set')
  assert.equal(formatAssignmentDate(undefined, 'None'), 'None')
  const formatted = formatAssignmentDate('2026-10-25T14:30:00Z')
  assert.ok(formatted.includes('2026'))
  assert.ok(formatted.includes('Oct') || formatted.includes('10'))
})

test('filterAssignments filters by search query and status', () => {
  const sample = [
    {
      id: '1',
      title: 'Database Assignment',
      course_name: 'Database Systems',
      course_code: 'CS101',
      status: 'active',
    },
    {
      id: '2',
      title: 'OS Process Viva',
      course_name: 'Operating Systems',
      course_code: 'CS201',
      status: 'scheduled',
    },
    {
      id: '3',
      title: 'Network Protocols',
      course_name: 'Networks',
      course_code: 'CS301',
      status: 'closed',
    },
  ]

  assert.equal(filterAssignments(sample, '', 'all').length, 3)
  assert.equal(filterAssignments(sample, 'database', 'all').length, 1)
  assert.equal(filterAssignments(sample, 'cs201', 'all').length, 1)
  assert.equal(filterAssignments(sample, '', 'scheduled').length, 1)
  assert.equal(filterAssignments(sample, '', 'closed').length, 1)
  assert.equal(filterAssignments(sample, 'nonexistent', 'all').length, 0)
})

test('getAssignmentSummaryStats tallies correctly', () => {
  const sample = [
    { status: 'active', total_submissions: 5 },
    { status: 'scheduled', total_submissions: 0 },
    { status: 'closed', total_submissions: 10 },
  ]

  const stats = getAssignmentSummaryStats(sample)
  assert.equal(stats.total, 3)
  assert.equal(stats.active, 1)
  assert.equal(stats.scheduled, 1)
  assert.equal(stats.closed, 1)
  assert.equal(stats.totalSubmissions, 15)
})
