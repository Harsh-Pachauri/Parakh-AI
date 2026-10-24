import { formatRatioPercent } from './formatters.js'

/**
 * Calculates summary metrics for student viva sessions.
 * Safely handles missing scores, partial sessions, and empty state.
 *
 * @param {Array<Object> | null | undefined} sessions
 * @returns {{
 *   totalAttempted: number,
 *   completedCount: number,
 *   inProgressCount: number,
 *   scoredCount: number,
 *   averageScore: number | null,
 *   averageScorePercent: string,
 *   averageScoreRatio: number,
 * }}
 */
export function calculateStudentStats(sessions) {
  if (!Array.isArray(sessions) || sessions.length === 0) {
    return {
      totalAttempted: 0,
      completedCount: 0,
      inProgressCount: 0,
      scoredCount: 0,
      averageScore: null,
      averageScorePercent: '—',
      averageScoreRatio: 0,
    }
  }

  const totalAttempted = sessions.length
  const completedSessions = sessions.filter((s) => s && s.status === 'completed')
  const completedCount = completedSessions.length
  const inProgressCount = totalAttempted - completedCount

  const scoredSessions = completedSessions.filter(
    (s) => s.total_score !== null && s.total_score !== undefined && !Number.isNaN(Number(s.total_score))
  )

  if (scoredSessions.length === 0) {
    return {
      totalAttempted,
      completedCount,
      inProgressCount,
      scoredCount: 0,
      averageScore: null,
      averageScorePercent: '—',
      averageScoreRatio: 0,
    }
  }

  const scoreSum = scoredSessions.reduce((acc, s) => acc + Number(s.total_score), 0)
  const rawAvg = scoreSum / scoredSessions.length
  const averageScore = Math.max(0, Math.min(1, Number(rawAvg.toFixed(4))))

  return {
    totalAttempted,
    completedCount,
    inProgressCount,
    scoredCount: scoredSessions.length,
    averageScore,
    averageScorePercent: formatRatioPercent(averageScore),
    averageScoreRatio: averageScore,
  }
}

/**
 * Filters a list of student sessions by lifecycle status.
 *
 * @param {Array<Object> | null | undefined} sessions
 * @param {'all' | 'completed' | 'in_progress'} filterStatus
 * @returns {Array<Object>}
 */
export function filterStudentSessions(sessions, filterStatus = 'all') {
  if (!Array.isArray(sessions)) return []

  const normalizedFilter = String(filterStatus || 'all').toLowerCase()
  if (normalizedFilter === 'completed') {
    return sessions.filter((s) => s && s.status === 'completed')
  }
  if (normalizedFilter === 'in_progress') {
    return sessions.filter((s) => s && s.status !== 'completed')
  }

  return [...sessions]
}

/**
 * Formats session timestamps safely into human-readable strings.
 *
 * @param {string | Date | null | undefined} dateInput
 * @returns {string}
 */
export function formatSessionDate(dateInput) {
  if (!dateInput) return '—'
  const date = new Date(dateInput)
  if (Number.isNaN(date.getTime())) return '—'

  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Extracts recent scored sessions for visual performance progression.
 *
 * @param {Array<Object> | null | undefined} sessions
 * @param {number} limit
 * @returns {Array<{
 *   id: string,
 *   courseName: string,
 *   score: number,
 *   scorePercent: string,
 *   ratio: number,
 *   date: string
 * }>}
 */
export function getRecentScoreTrend(sessions, limit = 5) {
  if (!Array.isArray(sessions) || sessions.length === 0) return []

  return sessions
    .filter((s) => s && s.status === 'completed' && s.total_score !== null && s.total_score !== undefined && !Number.isNaN(Number(s.total_score)))
    .slice(0, limit)
    .map((s) => {
      const numericScore = Number(s.total_score)
      const ratio = Math.max(0, Math.min(1, numericScore))
      return {
        id: s.id,
        courseName: s.course_name || s.course_code || 'Practice Viva',
        score: numericScore,
        scorePercent: formatRatioPercent(ratio),
        ratio,
        date: formatSessionDate(s.finished_at || s.created_at || s.started_at),
      }
    })
}
