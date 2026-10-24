/**
 * Helper utilities for Student and Teacher Detailed Performance Reports (P2.12).
 */

/**
 * Formats a 0.0 to 1.0 fractional score to percentage string, with fallback.
 * @param {number | null | undefined} score
 * @param {string} fallback
 * @returns {string}
 */
export function formatReportScore(score, fallback = '—') {
  if (score === null || score === undefined || isNaN(Number(score))) {
    return fallback
  }
  const clamped = Math.max(0, Math.min(1, Number(score)))
  return `${Math.round(clamped * 100)}%`
}

/**
 * Returns a CSS class name and descriptive label for performance tiers.
 * @param {number | null | undefined} score
 * @returns {{ label: string, className: string }}
 */
export function getPerformanceTier(score) {
  if (score === null || score === undefined || isNaN(Number(score))) {
    return { label: 'Unscored', className: 'tier-unscored' }
  }
  const val = Number(score)
  if (val >= 0.8) return { label: 'Mastery (80%+)', className: 'tier-mastery' }
  if (val >= 0.65) return { label: 'Proficient (65-79%)', className: 'tier-proficient' }
  if (val >= 0.5) return { label: 'Developing (50-64%)', className: 'tier-developing' }
  return { label: 'Needs Attention (<50%)', className: 'tier-attention' }
}

/**
 * Constructs a query string from filter object omitting empty/null keys.
 * @param {Record<string, any>} params
 * @returns {string}
 */
export function serializeReportParams(params = {}) {
  const searchParams = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && String(v).trim() !== '' && v !== 'all') {
      searchParams.append(k, String(v).trim())
    }
  }
  const qs = searchParams.toString()
  return qs ? `?${qs}` : ''
}

/**
 * Filters a list of report sessions by search keyword and session type.
 * @param {Array} sessions
 * @param {string} search
 * @param {string} typeFilter
 * @returns {Array}
 */
export function filterReportItems(sessions = [], search = '', typeFilter = 'all') {
  const q = (search || '').trim().toLowerCase()
  const filter = (typeFilter || 'all').toLowerCase()

  return sessions.filter((s) => {
    if (filter !== 'all' && (s.type || s.status || '').toLowerCase() !== filter) {
      return false
    }
    if (!q) return true
    const title = (s.title || '').toLowerCase()
    const course = (s.course_name || s.course_code || '').toLowerCase()
    const student = (s.student_name || s.student_email || '').toLowerCase()
    return title.includes(q) || course.includes(q) || student.includes(q)
  })
}

/**
 * Validates report date filters (ensuring from_date <= to_date).
 * @param {string} fromDate
 * @param {string} toDate
 * @returns {{ valid: boolean, error?: string }}
 */
export function validateDateRange(fromDate, toDate) {
  if (!fromDate || !toDate) return { valid: true }
  const d1 = new Date(fromDate)
  const d2 = new Date(toDate)
  if (isNaN(d1.getTime()) || isNaN(d2.getTime())) {
    return { valid: false, error: 'Invalid date format.' }
  }
  if (d1 > d2) {
    return { valid: false, error: 'Start date must be earlier than end date.' }
  }
  return { valid: true }
}
