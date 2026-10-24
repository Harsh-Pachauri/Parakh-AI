/**
 * Assessment and custom viva helper utilities.
 */

/**
 * Validates custom assessment form fields.
 * @param {object} form
 * @returns {{ valid: boolean, errors: Record<string, string> }}
 */
export function validateAssessmentForm(form) {
  const errors = {}

  const title = (form.title || '').trim()
  if (!title) {
    errors.title = 'Assessment title is required.'
  } else if (title.length > 255) {
    errors.title = 'Assessment title must be 255 characters or less.'
  }

  if (!form.course_id) {
    errors.course_id = 'Please select a course for this assessment.'
  }

  const duration = Number(form.duration_minutes)
  if (!duration || isNaN(duration) || duration < 1 || duration > 180) {
    errors.duration_minutes = 'Duration must be between 1 and 180 minutes.'
  }

  const maxQuestions = Number(form.max_questions)
  if (!maxQuestions || isNaN(maxQuestions) || maxQuestions < 1 || maxQuestions > 20) {
    errors.max_questions = 'Number of questions must be between 1 and 20.'
  }

  const difficulty = (form.difficulty || 'medium').toLowerCase()
  if (!['easy', 'medium', 'hard', 'adaptive'].includes(difficulty)) {
    errors.difficulty = 'Difficulty must be easy, medium, hard, or adaptive.'
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  }
}

/**
 * Formats published status into a readable label and CSS badge class.
 * @param {boolean} isPublished
 * @returns {{ label: string, className: string }}
 */
export function formatAssessmentStatus(isPublished) {
  return isPublished
    ? { label: 'Published', className: 'status-tag published' }
    : { label: 'Draft', className: 'status-tag draft' }
}

/**
 * Filter assessments by search keyword or course ID.
 * @param {Array} assessments
 * @param {string} query
 * @param {string} courseId
 * @returns {Array}
 */
export function filterAssessments(assessments, query = '', courseId = '') {
  if (!Array.isArray(assessments)) return []
  const q = (query || '').trim().toLowerCase()
  return assessments.filter((a) => {
    if (courseId && a.course_id !== courseId) return false
    if (!q) return true
    const titleMatch = (a.title || '').toLowerCase().includes(q)
    const courseMatch = (a.course_name || '').toLowerCase().includes(q)
    const codeMatch = (a.course_code || '').toLowerCase().includes(q)
    return titleMatch || courseMatch || codeMatch
  })
}

/**
 * Parses CSV text client-side for line count and format inspection.
 * @param {string} csvText
 * @returns {{ rowCount: number, hasHeader: boolean, warnings: string[] }}
 */
export function inspectCsvText(csvText) {
  if (!csvText || typeof csvText !== 'string') {
    return { rowCount: 0, hasHeader: false, warnings: ['CSV text is empty.'] }
  }
  const lines = csvText.split(/\r?\n/).filter((line) => line.trim().length > 0)
  if (lines.length === 0) {
    return { rowCount: 0, hasHeader: false, warnings: ['CSV text is empty.'] }
  }
  const header = lines[0].toLowerCase()
  const hasQuestionHeader = header.includes('question')
  const hasKeyPointsHeader = header.includes('expected') || header.includes('point') || header.includes('rubric')

  const warnings = []
  if (!hasQuestionHeader) {
    warnings.push('Header row should include a "question_text" column.')
  }
  if (!hasKeyPointsHeader) {
    warnings.push('Header row should include an "expected_key_points" or "explanation" column.')
  }

  return {
    rowCount: Math.max(0, lines.length - 1),
    hasHeader: hasQuestionHeader,
    warnings,
  }
}
