/**
 * Helper utilities for Platform Admin management.
 */

/**
 * Validates new institution form inputs.
 * @param {{ name?: string, code?: string }} form
 * @returns {{ isValid: boolean, error: string | null }}
 */
export function validateInstitutionForm({ name = '', code = '' } = {}) {
  const trimmedName = name.trim()
  if (!trimmedName || trimmedName.length < 2) {
    return { isValid: false, error: 'Institution name must be at least 2 characters.' }
  }
  if (trimmedName.length > 255) {
    return { isValid: false, error: 'Institution name cannot exceed 255 characters.' }
  }

  const trimmedCode = code.trim()
  if (!trimmedCode || trimmedCode.length < 2) {
    return { isValid: false, error: 'Institution code must be at least 2 characters.' }
  }
  if (trimmedCode.length > 50) {
    return { isValid: false, error: 'Institution code cannot exceed 50 characters.' }
  }

  return { isValid: true, error: null }
}

/**
 * Validates institution admin appointment form inputs.
 * @param {{ institution_id?: string, full_name?: string, email?: string, password?: string }} form
 * @returns {{ isValid: boolean, error: string | null }}
 */
export function validateInstitutionAdminForm({
  institution_id = '',
  full_name = '',
  email = '',
  password = '',
} = {}) {
  if (!institution_id || !institution_id.trim()) {
    return { isValid: false, error: 'Please select an institution.' }
  }

  const trimmedName = full_name.trim()
  if (!trimmedName) {
    return { isValid: false, error: 'Administrator full name is required.' }
  }

  const trimmedEmail = email.trim()
  if (!trimmedEmail) {
    return { isValid: false, error: 'Administrator email address is required.' }
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(trimmedEmail)) {
    return { isValid: false, error: 'Please enter a valid email address.' }
  }

  if (!password || password.length < 6) {
    return { isValid: false, error: 'Password must be at least 6 characters.' }
  }

  return { isValid: true, error: null }
}

/**
 * Formats API errors for platform administration actions.
 * @param {any} error
 * @param {'institution' | 'admin'} [context='institution']
 * @returns {string}
 */
export function formatPlatformAdminError(error, context = 'institution') {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail

  if (status === 409) {
    if (context === 'admin' || (typeof detail === 'string' && detail.toLowerCase().includes('email'))) {
      return 'A user with this email address is already registered.'
    }
    return 'An institution with this name or code already exists. Please choose a unique name and code.'
  }

  if (status === 404) {
    return 'The selected institution was not found.'
  }

  if (status === 403) {
    return 'Permission denied: platform administrator access required.'
  }

  return (
    error?.userMessage ||
    (typeof detail === 'string' ? detail : null) ||
    'The request could not be completed. Please try again.'
  )
}

/**
 * Filters a list of institutions by name or code.
 * @param {Array<{ name?: string, code?: string }>} institutions
 * @param {string} query
 * @returns {Array}
 */
export function filterInstitutions(institutions, query) {
  if (!Array.isArray(institutions)) return []
  if (!query || typeof query !== 'string') return institutions
  const term = query.trim().toLowerCase()
  if (!term) return institutions

  return institutions.filter((inst) => {
    if (!inst) return false
    const nameMatch = (inst.name || '').toLowerCase().includes(term)
    const codeMatch = (inst.code || '').toLowerCase().includes(term)
    return nameMatch || codeMatch
  })
}
