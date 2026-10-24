/**
 * Helper utilities for Institution Admin management.
 */

/**
 * Validates teacher creation form data.
 * @param {{ full_name?: string, email?: string, password?: string }} form
 * @returns {{ isValid: boolean, error: string | null }}
 */
export function validateTeacherForm({ full_name = '', email = '', password = '' } = {}) {
  const trimmedName = full_name.trim()
  if (!trimmedName) {
    return { isValid: false, error: 'Full name is required.' }
  }

  const trimmedEmail = email.trim()
  if (!trimmedEmail) {
    return { isValid: false, error: 'Email address is required.' }
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
 * Safely formats a teacher's creation timestamp into a consistent display date.
 * @param {string | Date | null | undefined} dateInput
 * @returns {string}
 */
export function formatTeacherDate(dateInput) {
  if (!dateInput) return '—'
  const date = new Date(dateInput)
  if (isNaN(date.getTime())) return '—'

  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * Filters a list of teachers by search query matching full_name or email.
 * Performs a case-insensitive substring search.
 * @param {Array<{ full_name?: string, email?: string }>} teachers
 * @param {string} query
 * @returns {Array}
 */
export function filterTeachers(teachers, query) {
  if (!Array.isArray(teachers)) return []
  if (!query || typeof query !== 'string') return teachers
  const term = query.trim().toLowerCase()
  if (!term) return teachers

  return teachers.filter((teacher) => {
    if (!teacher) return false
    const nameMatch = (teacher.full_name || '').toLowerCase().includes(term)
    const emailMatch = (teacher.email || '').toLowerCase().includes(term)
    return nameMatch || emailMatch
  })
}

/**
 * Formats a registration error into a clear and actionable message.
 * @param {any} error
 * @param {string} email
 * @returns {string}
 */
export function formatTeacherRegistrationError(error, email = '') {
  if (error?.response?.status === 409) {
    const cleanEmail = email ? ` "${email.trim()}"` : ''
    return `A user with email${cleanEmail} is already registered in the system. Please use a different email address.`
  }
  return (
    error?.userMessage ||
    error?.response?.data?.detail ||
    'Could not register teacher. Please verify details and try again.'
  )
}
