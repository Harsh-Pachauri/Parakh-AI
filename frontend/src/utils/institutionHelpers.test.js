import test from 'node:test'
import assert from 'node:assert'
import {
  validateTeacherForm,
  formatTeacherDate,
  filterTeachers,
  formatTeacherRegistrationError,
} from './institutionHelpers.js'

test('validateTeacherForm accepts valid teacher data', () => {
  const result = validateTeacherForm({
    full_name: 'Dr. Jane Doe',
    email: 'jane.doe@university.edu',
    password: 'securePassword123',
  })
  assert.strictEqual(result.isValid, true)
  assert.strictEqual(result.error, null)
})

test('validateTeacherForm trims inputs properly', () => {
  const result = validateTeacherForm({
    full_name: '   Prof. Alan Turing   ',
    email: '  alan@cambridge.ac.uk  ',
    password: 'password123',
  })
  assert.strictEqual(result.isValid, true)
  assert.strictEqual(result.error, null)
})

test('validateTeacherForm rejects empty or missing full name', () => {
  const empty = validateTeacherForm({
    full_name: '   ',
    email: 'test@example.com',
    password: 'password123',
  })
  assert.strictEqual(empty.isValid, false)
  assert.strictEqual(empty.error, 'Full name is required.')

  const missing = validateTeacherForm({
    email: 'test@example.com',
    password: 'password123',
  })
  assert.strictEqual(missing.isValid, false)
  assert.strictEqual(missing.error, 'Full name is required.')
})

test('validateTeacherForm rejects empty or invalid email', () => {
  const empty = validateTeacherForm({
    full_name: 'Dr. Smith',
    email: '   ',
    password: 'password123',
  })
  assert.strictEqual(empty.isValid, false)
  assert.strictEqual(empty.error, 'Email address is required.')

  const invalid = validateTeacherForm({
    full_name: 'Dr. Smith',
    email: 'not-an-email',
    password: 'password123',
  })
  assert.strictEqual(invalid.isValid, false)
  assert.strictEqual(invalid.error, 'Please enter a valid email address.')
})

test('validateTeacherForm rejects password shorter than 6 characters', () => {
  const short = validateTeacherForm({
    full_name: 'Dr. Smith',
    email: 'smith@example.com',
    password: '12345',
  })
  assert.strictEqual(short.isValid, false)
  assert.strictEqual(short.error, 'Password must be at least 6 characters.')

  const empty = validateTeacherForm({
    full_name: 'Dr. Smith',
    email: 'smith@example.com',
    password: '',
  })
  assert.strictEqual(empty.isValid, false)
  assert.strictEqual(empty.error, 'Password must be at least 6 characters.')
})

test('formatTeacherDate formats valid ISO dates correctly', () => {
  assert.strictEqual(formatTeacherDate('2026-10-23T12:00:00Z'), 'Oct 23, 2026')
  assert.strictEqual(formatTeacherDate('2025-01-05T00:00:00Z'), 'Jan 5, 2025')
})

test('formatTeacherDate safely handles invalid or missing dates', () => {
  assert.strictEqual(formatTeacherDate(null), '—')
  assert.strictEqual(formatTeacherDate(undefined), '—')
  assert.strictEqual(formatTeacherDate(''), '—')
  assert.strictEqual(formatTeacherDate('invalid-date-string'), '—')
})

const sampleTeachers = [
  { id: '1', full_name: 'Dr. Priya Sharma', email: 'priya@university.edu' },
  { id: '2', full_name: 'Prof. Alan Turing', email: 'alan@cambridge.ac.uk' },
  { id: '3', full_name: 'Dr. Marie Curie', email: 'marie@sorbonne.fr' },
]

test('filterTeachers returns all teachers when query is empty or whitespace', () => {
  assert.deepStrictEqual(filterTeachers(sampleTeachers, ''), sampleTeachers)
  assert.deepStrictEqual(filterTeachers(sampleTeachers, '   '), sampleTeachers)
  assert.deepStrictEqual(filterTeachers(sampleTeachers, null), sampleTeachers)
  assert.deepStrictEqual(filterTeachers(sampleTeachers, undefined), sampleTeachers)
})

test('filterTeachers matches case-insensitively by full name', () => {
  const result = filterTeachers(sampleTeachers, 'priya')
  assert.strictEqual(result.length, 1)
  assert.strictEqual(result[0].id, '1')

  const upperResult = filterTeachers(sampleTeachers, 'TURING')
  assert.strictEqual(upperResult.length, 1)
  assert.strictEqual(upperResult[0].id, '2')
})

test('filterTeachers matches case-insensitively by email', () => {
  const result = filterTeachers(sampleTeachers, 'sorbonne.fr')
  assert.strictEqual(result.length, 1)
  assert.strictEqual(result[0].id, '3')
})

test('filterTeachers returns empty array when no matches found', () => {
  const result = filterTeachers(sampleTeachers, 'nonexistent')
  assert.strictEqual(result.length, 0)
})

test('filterTeachers safely handles invalid teacher list inputs', () => {
  assert.deepStrictEqual(filterTeachers(null, 'query'), [])
  assert.deepStrictEqual(filterTeachers(undefined, 'query'), [])
})

test('formatTeacherRegistrationError handles 409 Conflict duplicate emails', () => {
  const err409 = {
    response: {
      status: 409,
      data: { detail: 'Email is already registered' },
    },
  }
  const msg = formatTeacherRegistrationError(err409, 'existing@viva.edu')
  assert.strictEqual(
    msg,
    'A user with email "existing@viva.edu" is already registered in the system. Please use a different email address.'
  )
})

test('formatTeacherRegistrationError handles general and fallback errors', () => {
  const errCustom = { userMessage: 'Service temporarily unavailable.' }
  assert.strictEqual(formatTeacherRegistrationError(errCustom), 'Service temporarily unavailable.')

  const emptyErr = {}
  assert.strictEqual(
    formatTeacherRegistrationError(emptyErr),
    'Could not register teacher. Please verify details and try again.'
  )
})
