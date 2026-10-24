/**
 * Helper utilities for Adaptive AI Viva practice and learning summaries.
 */

/**
 * Returns label and CSS styling class for a difficulty level.
 *
 * @param {'easy' | 'medium' | 'hard' | string | null | undefined} difficulty
 * @returns {{ label: string, colorClass: string }}
 */
export function formatDifficultyBadge(difficulty) {
  const norm = String(difficulty || 'medium').toLowerCase()
  if (norm === 'easy') {
    return { label: 'Foundational (Easy)', colorClass: 'diff-tag easy' }
  }
  if (norm === 'hard') {
    return { label: 'Advanced (Hard)', colorClass: 'diff-tag hard' }
  }
  return { label: 'Intermediate (Medium)', colorClass: 'diff-tag medium' }
}

/**
 * Formats a sequence of difficulty adjustments into a step-by-step progression trace.
 *
 * @param {Array<string> | null | undefined} progression
 * @returns {Array<{ step: number, difficulty: string, label: string }>}
 */
export function formatDifficultyProgression(progression) {
  if (!Array.isArray(progression) || progression.length === 0) {
    return [{ step: 1, difficulty: 'medium', label: 'Medium' }]
  }

  return progression.map((diff, index) => {
    const norm = String(diff || 'medium').toLowerCase()
    const cap = norm.charAt(0).toUpperCase() + norm.slice(1)
    return {
      step: index + 1,
      difficulty: norm,
      label: cap,
    }
  })
}

/**
 * Checks whether a session object represents an adaptive viva practice session.
 *
 * @param {Object | null | undefined} session
 * @returns {boolean}
 */
export function isAdaptiveSession(session) {
  if (!session || typeof session !== 'object') return false
  if (session.is_adaptive !== undefined) return Boolean(session.is_adaptive)
  // Fallback to checking config if present
  if (session.config && typeof session.config === 'object') {
    if (session.config.is_adaptive !== undefined) return Boolean(session.config.is_adaptive)
    if (session.config.assessment_id || session.config.assignment_id) return false
  }
  return !session.assessment_id && !session.assignment_id
}

/**
 * Analyzes an adaptive summary to extract key progress indicators and takeaways.
 *
 * @param {Object | null | undefined} summary
 * @returns {{
 *   hasImprovement: boolean,
 *   improvedCount: number,
 *   attentionCount: number,
 *   note: string
 * }}
 */
export function summarizeAdaptiveProgress(summary) {
  if (!summary || typeof summary !== 'object') {
    return {
      hasImprovement: false,
      improvedCount: 0,
      attentionCount: 0,
      note: 'Adaptive practice data is currently unavailable.',
    }
  }

  const improvedCount = Array.isArray(summary.topics_showing_improvement)
    ? summary.topics_showing_improvement.length
    : 0
  const attentionCount = Array.isArray(summary.topics_needing_attention)
    ? summary.topics_needing_attention.length
    : 0

  let note = summary.insufficient_data_note || ''
  if (!note) {
    if (improvedCount > 0) {
      note = `Great progress! Demonstrated notable concept mastery improvement in ${improvedCount} topic${improvedCount > 1 ? 's' : ''}.`
    } else if (attentionCount > 0) {
      note = `Identified ${attentionCount} area${attentionCount > 1 ? 's' : ''} for targeted revision before your next oral exam.`
    } else {
      note = 'Performance remained stable across practiced syllabus topics.'
    }
  }

  return {
    hasImprovement: improvedCount > 0,
    improvedCount,
    attentionCount,
    note,
  }
}

/**
 * Constructs an adaptive practice viva URL.
 *
 * @param {string | null | undefined} courseId
 * @param {string | null | undefined} [topicId]
 * @returns {string}
 */
export function buildAdaptivePracticeUrl(courseId, topicId) {
  if (!courseId) return '/'
  if (!topicId) return `/viva/${courseId}?mode=adaptive`
  return `/viva/${courseId}?topic=${topicId}&mode=adaptive`
}
