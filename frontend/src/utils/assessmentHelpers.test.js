import test from 'node:test'
import assert from 'node:assert/strict'
import {
  validateAssessmentForm,
  formatAssessmentStatus,
  filterAssessments,
  inspectCsvText,
} from './assessmentHelpers.js'

test('validateAssessmentForm accepts valid assessment data', () => {
  const form = {
    title: 'Operating Systems Midterm',
    course_id: 'course-123',
    duration_minutes: 20,
    max_questions: 5,
    difficulty: 'medium',
  }
  const result = validateAssessmentForm(form)
  assert.equal(result.valid, true)
  assert.deepEqual(result.errors, {})
})

test('validateAssessmentForm rejects missing title or course_id', () => {
  const form = {
    title: '   ',
    course_id: '',
    duration_minutes: 20,
    max_questions: 5,
    difficulty: 'medium',
  }
  const result = validateAssessmentForm(form)
  assert.equal(result.valid, false)
  assert.ok(result.errors.title)
  assert.ok(result.errors.course_id)
})

test('validateAssessmentForm rejects out-of-range duration or question counts', () => {
  const form = {
    title: 'Final Exam',
    course_id: 'c1',
    duration_minutes: 0,
    max_questions: 25,
    difficulty: 'invalid',
  }
  const result = validateAssessmentForm(form)
  assert.equal(result.valid, false)
  assert.ok(result.errors.duration_minutes)
  assert.ok(result.errors.max_questions)
  assert.ok(result.errors.difficulty)
})

test('formatAssessmentStatus formats draft and published states', () => {
  const pub = formatAssessmentStatus(true)
  assert.equal(pub.label, 'Published')
  assert.ok(pub.className.includes('published'))

  const draft = formatAssessmentStatus(false)
  assert.equal(draft.label, 'Draft')
  assert.ok(draft.className.includes('draft'))
})

test('filterAssessments matches by title, course name, or code', () => {
  const items = [
    { id: '1', title: 'Data Structures Midterm', course_id: 'c1', course_name: 'DSA', course_code: 'CS101' },
    { id: '2', title: 'Algorithms Final', course_id: 'c2', course_name: 'Advanced Algo', course_code: 'CS202' },
  ]
  assert.equal(filterAssessments(items, 'midterm').length, 1)
  assert.equal(filterAssessments(items, 'cs202').length, 1)
  assert.equal(filterAssessments(items, '', 'c1').length, 1)
  assert.equal(filterAssessments(items, 'nomatch').length, 0)
  assert.deepEqual(filterAssessments(null), [])
})

test('inspectCsvText detects headers and counts rows', () => {
  const csv = 'question_text,expected_key_points,difficulty\n"Q1","Point 1",medium\n"Q2","Point 2",easy'
  const res = inspectCsvText(csv)
  assert.equal(res.rowCount, 2)
  assert.equal(res.hasHeader, true)
  assert.equal(res.warnings.length, 0)

  const empty = inspectCsvText('')
  assert.equal(empty.rowCount, 0)
  assert.ok(empty.warnings.length > 0)
})
