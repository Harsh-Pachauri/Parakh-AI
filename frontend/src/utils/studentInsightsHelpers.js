/**
 * Helper utilities for AI-powered student weakness detection and recommendations.
 */

/**
 * Normalizes and caps recommendations for presentation.
 *
 * @param {Array<Object> | null | undefined} recommendations
 * @param {number} [maxCount=3]
 * @returns {Array<Object>}
 */
export function filterRecommendations(recommendations, maxCount = 3) {
  if (!Array.isArray(recommendations)) return []
  return recommendations.slice(0, maxCount)
}

/**
 * Returns badge styling and label for a topic classification.
 *
 * @param {'weakness' | 'strength' | 'developing' | string} status
 * @returns {{ label: string, colorClass: string }}
 */
export function getTopicStatusBadge(status) {
  const norm = String(status || '').toLowerCase()
  if (norm === 'weakness') {
    return { label: 'Needs Focus', colorClass: 'status-tag in_progress' }
  }
  if (norm === 'strength') {
    return { label: 'Strong Mastery', colorClass: 'status-tag completed' }
  }
  if (norm === 'developing') {
    return { label: 'Developing', colorClass: 'status-tag' }
  }
  return { label: 'Untested', colorClass: 'status-tag' }
}

/**
 * Formats dimension breakdown scores into human-readable text.
 *
 * @param {{ correctness?: number | null, completeness?: number | null, clarity?: number | null } | null | undefined} dims
 * @returns {string}
 */
export function formatDimensionSummary(dims) {
  if (!dims || typeof dims !== 'object') return 'Evaluation dimensions unavailable'

  const parts = []
  if (typeof dims.correctness === 'number') {
    parts.push(`Accuracy: ${dims.correctness.toFixed(1)}/10`)
  }
  if (typeof dims.completeness === 'number') {
    parts.push(`Completeness: ${dims.completeness.toFixed(1)}/10`)
  }
  if (typeof dims.clarity === 'number') {
    parts.push(`Clarity: ${dims.clarity.toFixed(1)}/10`)
  }

  return parts.length ? parts.join(' · ') : 'Evaluation dimensions unavailable'
}

/**
 * Constructs a safe viva practice URL with optional topic selection.
 *
 * @param {string | null | undefined} courseId
 * @param {string | null | undefined} [topicId]
 * @returns {string}
 */
export function buildPracticeUrl(courseId, topicId) {
  if (!courseId) return '/'
  if (!topicId) return `/viva/${courseId}`
  return `/viva/${courseId}?topic=${topicId}`
}
