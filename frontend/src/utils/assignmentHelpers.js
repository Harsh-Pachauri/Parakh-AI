/**
 * Assessment Assignment, Scheduling, and Deadlines helper utilities (P2.11).
 */

/**
 * Validates assignment form fields before submission.
 * @param {object} form
 * @returns {{ valid: boolean, errors: Record<string, string> }}
 */
export function validateAssignmentForm(form) {
  const errors = {}

  const title = (form.title || '').trim()
  if (!title) {
    errors.title = 'Assignment title is required.'
  } else if (title.length > 255) {
    errors.title = 'Assignment title must be 255 characters or less.'
  }

  if (!form.course_id) {
    errors.course_id = 'Please select a course for this assignment.'
  }

  if (!form.assessment_id) {
    errors.assessment_id = 'Please select a published custom assessment.'
  }

  const attemptLimit = Number(form.attempt_limit)
  if (!attemptLimit || isNaN(attemptLimit) || attemptLimit < 1 || attemptLimit > 100) {
    errors.attempt_limit = 'Attempt limit must be between 1 and 100.'
  }

  if (form.start_date && form.deadline) {
    const start = new Date(form.start_date)
    const deadline = new Date(form.deadline)
    if (isNaN(start.getTime())) {
      errors.start_date = 'Invalid start date format.'
    }
    if (isNaN(deadline.getTime())) {
      errors.deadline = 'Invalid deadline format.'
    }
    if (!errors.start_date && !errors.deadline && start >= deadline) {
      errors.deadline = 'Deadline must be later than the scheduled start date.'
    }
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  }
}

/**
 * Formats assignment status into readable display label and CSS class name.
 * @param {string} status
 * @returns {{ label: string, className: string }}
 */
export function formatAssignmentStatus(status) {
  switch ((status || '').toLowerCase()) {
    case 'active':
      return { label: 'Active', className: 'status-tag published' }
    case 'available':
      return { label: 'Available Now', className: 'status-tag published' }
    case 'scheduled':
      return { label: 'Scheduled', className: 'status-tag info' }
    case 'submitted':
      return { label: 'Submitted', className: 'status-tag submitted' }
    case 'overdue':
      return { label: 'Overdue', className: 'status-tag danger' }
    case 'closed':
      return { label: 'Closed', className: 'status-tag draft' }
    default:
      return { label: status || 'Unknown', className: 'status-tag default' }
  }
}

/**
 * Formats ISO datetime string to user-friendly local date and time.
 * @param {string | null | undefined} isoString
 * @param {string} fallback
 * @returns {string}
 */
export function formatAssignmentDate(isoString, fallback = 'No date set') {
  if (!isoString) return fallback
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return fallback
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Filters a list of assignments by search keyword and status filter.
 * @param {Array} assignments
 * @param {string} query
 * @param {string} statusFilter
 * @returns {Array}
 */
export function filterAssignments(assignments = [], query = '', statusFilter = 'all') {
  const q = (query || '').trim().toLowerCase()
  const filter = (statusFilter || 'all').toLowerCase()

  return assignments.filter((item) => {
    if (filter !== 'all' && (item.status || '').toLowerCase() !== filter) {
      return false
    }

    if (!q) return true

    const title = (item.title || '').toLowerCase()
    const courseName = (item.course_name || '').toLowerCase()
    const courseCode = (item.course_code || '').toLowerCase()
    const assessTitle = (item.assessment_title || '').toLowerCase()

    return (
      title.includes(q) ||
      courseName.includes(q) ||
      courseCode.includes(q) ||
      assessTitle.includes(q)
    )
  })
}

/**
 * Computes assignment statistics summary.
 * @param {Array} assignments
 * @returns {{ total: number, active: number, scheduled: number, closed: number, totalSubmissions: number }}
 */
export function getAssignmentSummaryStats(assignments = []) {
  let active = 0
  let scheduled = 0
  let closed = 0
  let totalSubmissions = 0

  for (const a of assignments) {
    const st = (a.status || '').toLowerCase()
    if (st === 'active' || st === 'available') active++
    else if (st === 'scheduled') scheduled++
    else if (st === 'closed' || st === 'overdue') closed++

    totalSubmissions += Number(a.total_submissions || 0)
  }

  return {
    total: assignments.length,
    active,
    scheduled,
    closed,
    totalSubmissions,
  }
}
