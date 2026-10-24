import { formatRatioPercent } from './formatters.js'

/**
 * Filters a list of students by name or email.
 *
 * @param {Array<Object> | null | undefined} students
 * @param {string} query
 * @returns {Array<Object>}
 */
export function filterStudents(students, query = '') {
  if (!Array.isArray(students)) return []
  const trimmed = (query || '').trim().toLowerCase()
  if (!trimmed) return [...students]

  return students.filter((s) => {
    const nameMatch = (s.student_name || '').toLowerCase().includes(trimmed)
    const emailMatch = (s.student_email || '').toLowerCase().includes(trimmed)
    return nameMatch || emailMatch
  })
}

/**
 * Filters sessions by relative date range.
 *
 * @param {Array<Object> | null | undefined} sessions
 * @param {'all' | '7d' | '30d'} range
 * @param {number} [nowTimestamp] - Optional reference timestamp for testing
 * @returns {Array<Object>}
 */
export function filterSessionsByDateRange(sessions, range = 'all', nowTimestamp = Date.now()) {
  if (!Array.isArray(sessions)) return []
  if (!range || range === 'all') return [...sessions]

  const cutoffDays = range === '7d' ? 7 : range === '30d' ? 30 : 0
  if (cutoffDays === 0) return [...sessions]

  const cutoffTime = nowTimestamp - cutoffDays * 24 * 60 * 60 * 1000

  return sessions.filter((s) => {
    const timestampStr = s.finished_at || s.created_at || s.started_at
    if (!timestampStr) return false
    const time = new Date(timestampStr).getTime()
    return !Number.isNaN(time) && time >= cutoffTime
  })
}

/**
 * Calculates score performance distribution tiers across completed scored sessions.
 *
 * @param {Array<Object> | null | undefined} sessions
 * @returns {{
 *   needsAttention: number,
 *   developing: number,
 *   proficient: number,
 *   mastery: number,
 *   totalScored: number,
 * }}
 */
export function calculateScoreDistribution(sessions) {
  const result = {
    needsAttention: 0, // < 50%
    developing: 0,     // 50% - 69%
    proficient: 0,     // 70% - 84%
    mastery: 0,        // 85% - 100%
    totalScored: 0,
  }

  if (!Array.isArray(sessions)) return result

  for (const s of sessions) {
    if (s && s.status === 'completed' && s.total_score !== null && s.total_score !== undefined) {
      const num = Number(s.total_score)
      if (!Number.isNaN(num)) {
        result.totalScored += 1
        if (num < 0.50) {
          result.needsAttention += 1
        } else if (num < 0.70) {
          result.developing += 1
        } else if (num < 0.85) {
          result.proficient += 1
        } else {
          result.mastery += 1
        }
      }
    }
  }

  return result
}

/**
 * Calculates a student's score progression trajectory if sufficient real data exists (>= 2 scored sessions).
 *
 * @param {Array<Object> | null | undefined} sessions
 * @param {number} [limit=6]
 * @returns {{
 *   hasTrend: boolean,
 *   progress: Array<{ id: string, courseName: string, score: number, scorePercent: string, date: string, ratio: number }>,
 *   delta: number | null,
 *   deltaPercent: string,
 *   direction: 'up' | 'down' | 'flat',
 * }}
 */
export function getStudentScoreProgress(sessions, limit = 6) {
  const defaultEmpty = {
    hasTrend: false,
    progress: [],
    delta: null,
    deltaPercent: '—',
    direction: 'flat',
  }

  if (!Array.isArray(sessions)) return defaultEmpty

  const scored = sessions
    .filter((s) => s && s.status === 'completed' && s.total_score !== null && s.total_score !== undefined && !Number.isNaN(Number(s.total_score)))
    .map((s) => {
      const num = Number(s.total_score)
      const ratio = Math.max(0, Math.min(1, num))
      const time = new Date(s.finished_at || s.created_at || s.started_at || 0).getTime()
      return {
        id: s.id,
        courseName: s.course_name || s.course_code || 'Viva',
        score: num,
        scorePercent: formatRatioPercent(ratio),
        date: new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        timestamp: time,
        ratio,
      }
    })
    .sort((a, b) => a.timestamp - b.timestamp) // Chronological order
    .slice(-limit)

  if (scored.length < 2) {
    return {
      hasTrend: false,
      progress: scored,
      delta: null,
      deltaPercent: '—',
      direction: 'flat',
    }
  }

  const firstScore = scored[0].score
  const lastScore = scored[scored.length - 1].score
  const delta = Number((lastScore - firstScore).toFixed(4))
  const deltaPct = Math.round(delta * 100)
  const deltaPercent = `${deltaPct > 0 ? '+' : ''}${deltaPct}%`
  const direction = delta > 0.02 ? 'up' : delta < -0.02 ? 'down' : 'flat'

  return {
    hasTrend: true,
    progress: scored,
    delta,
    deltaPercent,
    direction,
  }
}
