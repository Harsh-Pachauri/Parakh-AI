import test from 'node:test'
import assert from 'node:assert'
import {
  validateInstitutionForm,
  validateInstitutionAdminForm,
  formatPlatformAdminError,
  filterInstitutions,
} from './platformAdminHelpers.js'

test('validateInstitutionForm accepts valid institution data', () => {
  const result = validateInstitutionForm({
    name: 'Indian Institute of Technology',
    code: 'IIT',
  })
  assert.strictEqual(result.isValid, true)
  assert.strictEqual(result.error, null)
})

test('validateInstitutionForm trims whitespace before checking length', () => {
  const result = validateInstitutionForm({
    name: '   Delhi University   ',
    code: '  DU  ',
  })
  assert.strictEqual(result.isValid, true)
  assert.strictEqual(result.error, null)
})

test('validateInstitutionForm rejects empty or short name', () => {
  const empty = validateInstitutionForm({ name: '', code: 'IIT' })
  assert.strictEqual(empty.isValid, false)
  assert.strictEqual(empty.error, 'Institution name must be at least 2 characters.')

  const short = validateInstitutionForm({ name: 'A', code: 'IIT' })
  assert.strictEqual(short.isValid, false)
  assert.strictEqual(short.error, 'Institution name must be at least 2 characters.')
})

test('validateInstitutionForm rejects empty or short code', () => {
  const empty = validateInstitutionForm({ name: 'Valid Name', code: '' })
  assert.strictEqual(empty.isValid, false)
  assert.strictEqual(empty.error, 'Institution code must be at least 2 characters.')

  const short = validateInstitutionForm({ name: 'Valid Name', code: 'X' })
  assert.strictEqual(short.isValid, false)
  assert.strictEqual(short.error, 'Institution code must be at least 2 characters.')
})

test('validateInstitutionAdminForm accepts valid admin data', () => {
  const result = validateInstitutionAdminForm({
    institution_id: '123e4567-e89b-12d3-a456-426614174000',
    full_name: 'Dr. Jane Provost',
    email: 'provost@university.edu',
    password: 'password123',
  })
  assert.strictEqual(result.isValid, true)
  assert.strictEqual(result.error, null)
})

test('validateInstitutionAdminForm rejects missing institution selection', () => {
  const noInst = validateInstitutionAdminForm({
    institution_id: '',
    full_name: 'Dr. Jane Provost',
    email: 'provost@university.edu',
    password: 'password123',
  })
  assert.strictEqual(noInst.isValid, false)
  assert.strictEqual(noInst.error, 'Please select an institution.')
})

test('validateInstitutionAdminForm rejects missing name or invalid email', () => {
  const noName = validateInstitutionAdminForm({
    institution_id: 'inst-1',
    full_name: '   ',
    email: 'provost@university.edu',
    password: 'password123',
  })
  assert.strictEqual(noName.isValid, false)
  assert.strictEqual(noName.error, 'Administrator full name is required.')

  const badEmail = validateInstitutionAdminForm({
    institution_id: 'inst-1',
    full_name: 'Dr. Provost',
    email: 'not-an-email',
    password: 'password123',
  })
  assert.strictEqual(badEmail.isValid, false)
  assert.strictEqual(badEmail.error, 'Please enter a valid email address.')
})

test('validateInstitutionAdminForm rejects short password', () => {
  const shortPass = validateInstitutionAdminForm({
    institution_id: 'inst-1',
    full_name: 'Dr. Provost',
    email: 'provost@university.edu',
    password: '12345',
  })
  assert.strictEqual(shortPass.isValid, false)
  assert.strictEqual(shortPass.error, 'Password must be at least 6 characters.')
})

test('formatPlatformAdminError handles 409 conflict for institutions and admins', () => {
  const instConflict = {
    response: {
      status: 409,
      data: { detail: 'An institution with this name or code already exists' },
    },
  }
  assert.strictEqual(
    formatPlatformAdminError(instConflict, 'institution'),
    'An institution with this name or code already exists. Please choose a unique name and code.'
  )

  const adminConflict = {
    response: {
      status: 409,
      data: { detail: 'Email is already registered' },
    },
  }
  assert.strictEqual(
    formatPlatformAdminError(adminConflict, 'admin'),
    'A user with this email address is already registered.'
  )
})

test('formatPlatformAdminError handles 404, 403 and fallbacks', () => {
  assert.strictEqual(
    formatPlatformAdminError({ response: { status: 404 } }),
    'The selected institution was not found.'
  )
  assert.strictEqual(
    formatPlatformAdminError({ response: { status: 403 } }),
    'Permission denied: platform administrator access required.'
  )
  assert.strictEqual(
    formatPlatformAdminError({ userMessage: 'Service offline' }),
    'Service offline'
  )
})

const sampleInstitutions = [
  { id: '1', name: 'St. Xavier College', code: 'SXC' },
  { id: '2', name: 'National Institute of Tech', code: 'NIT' },
  { id: '3', name: 'Oxford Academy', code: 'OXA' },
]

test('filterInstitutions matches by name and code case-insensitively', () => {
  assert.deepStrictEqual(filterInstitutions(sampleInstitutions, ''), sampleInstitutions)
  assert.deepStrictEqual(filterInstitutions(sampleInstitutions, '   '), sampleInstitutions)

  const byName = filterInstitutions(sampleInstitutions, 'xavier')
  assert.strictEqual(byName.length, 1)
  assert.strictEqual(byName[0].code, 'SXC')

  const byCode = filterInstitutions(sampleInstitutions, 'nit')
  assert.strictEqual(byCode.length, 1)
  assert.strictEqual(byCode[0].id, '2')
})

test('filterInstitutions handles empty matches and invalid inputs safely', () => {
  assert.strictEqual(filterInstitutions(sampleInstitutions, 'nonexistent').length, 0)
  assert.deepStrictEqual(filterInstitutions(null, 'query'), [])
  assert.deepStrictEqual(filterInstitutions(undefined, 'query'), [])
})
