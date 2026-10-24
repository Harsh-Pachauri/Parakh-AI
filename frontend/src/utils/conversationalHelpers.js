/**
 * Conversational utilities for humanized greetings, empathetic turn responses, and closings.
 */

const DASHBOARD_GREETINGS = [
  (name) => `Hey ${name}! Ready to test what you've learned today?`,
  (name) => `Welcome back, ${name}! Let's keep building your confidence.`,
  (name) => `Hi ${name}! Don't worry about getting everything perfect. Let's learn as we go.`,
  (name) => `Good to see you, ${name}! Pick a topic whenever you're ready to practice.`,
  (name) => `Hey ${name}! Let's strengthen your oral exam skills today.`,
]

/**
 * Returns a friendly, time-aware, personalized greeting for the student dashboard.
 *
 * @param {string | null | undefined} studentName
 * @param {number} [sessionCount=0]
 * @param {number} [hourOfDay=new Date().getHours()]
 * @returns {string}
 */
export function getStudentDashboardGreeting(
  studentName,
  sessionCount = 0,
  hourOfDay = new Date().getHours()
) {
  const name = studentName ? String(studentName).trim().split(' ')[0] : 'there'

  if (sessionCount === 0) {
    return `Welcome, ${name}! Don't worry about getting everything perfect. Let's learn as we go.`
  }

  // Time-of-day contextual variation
  if (hourOfDay < 12) {
    return `Good morning, ${name}! Great time for a quick viva practice run.`
  }
  if (hourOfDay >= 17) {
    return `Good evening, ${name}! Ready to test what you've learned today?`
  }

  // Pick deterministic greeting based on day of month to avoid jarring changes per reload
  const dayIndex = new Date().getDate() % DASHBOARD_GREETINGS.length
  return DASHBOARD_GREETINGS[dayIndex](name)
}

/**
 * Returns a human-like opening line to introduce a viva session naturally.
 *
 * @param {string | null | undefined} studentName
 * @param {boolean} [isAdaptive=true]
 * @param {string | null | undefined} [assessmentTitle]
 * @returns {string}
 */
export function getVivaOpeningGreeting(studentName, isAdaptive = true, assessmentTitle = '') {
  const name = studentName ? String(studentName).trim().split(' ')[0] : ''

  if (!isAdaptive && assessmentTitle) {
    return name
      ? `Welcome to ${assessmentTitle}, ${name}. Take your time and answer in your own words.`
      : `Welcome to ${assessmentTitle}. Take your time and answer in your own words.`
  }

  return name
    ? `Hey ${name}! Welcome to your viva. Take a breath, relax, and answer in your own words.`
    : `Hey! Welcome to your viva. Take a breath, relax, and answer in your own words.`
}

/**
 * Returns a warm, personalized closing message based on session score.
 *
 * @param {number | null | undefined} totalScore
 * @param {string | null | undefined} studentName
 * @param {number} [answerCount=0]
 * @returns {string}
 */
export function getCompletionClosingMessage(totalScore, studentName, answerCount = 0) {
  const name = studentName ? String(studentName).trim().split(' ')[0] : ''

  if (totalScore === null || totalScore === undefined || answerCount === 0) {
    return name
      ? `That concludes our session, ${name}. Your practice feedback is ready below.`
      : 'That concludes our session. Your practice feedback is ready below.'
  }

  const scoreNum = Number(totalScore)
  if (scoreNum >= 0.75) {
    return name
      ? `Outstanding work, ${name}! You demonstrated strong mastery across these concepts.`
      : 'Outstanding work! You demonstrated strong mastery across these concepts.'
  }

  if (scoreNum >= 0.50) {
    return name
      ? `Good session, ${name}! You've got solid foundations. Check out the feedback below to polish a few details.`
      : "Good session! You've got solid foundations. Check out the feedback below to polish a few details."
  }

  return name
    ? `Good work showing up and giving it your best try, ${name}. Review the suggestions below and practice again whenever you're ready.`
    : "Good work showing up and giving it your best try. Review the suggestions below and practice again whenever you're ready."
}
