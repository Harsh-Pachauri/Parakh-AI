import { useEffect, useState } from 'react'
import StudentPerformanceReportModal from '../components/StudentPerformanceReportModal'
import {
  formatAssignmentDate,
  formatAssignmentStatus,
} from '../utils/assignmentHelpers'
import apiClient from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { formatRatioPercent } from '../utils/formatters'
import { buildAdaptivePracticeUrl } from '../utils/adaptiveHelpers'
import { getStudentDashboardGreeting } from '../utils/conversationalHelpers'
import {
  buildPracticeUrl,
  formatDimensionSummary,
  getTopicStatusBadge,
} from '../utils/studentInsightsHelpers'
import {
  calculateStudentStats,
  filterStudentSessions,
  formatSessionDate,
  getRecentScoreTrend,
} from '../utils/studentProgressHelpers'

export default function StudentDashboard({ navigate }) {
  const { user } = useAuth()
  const [courses, setCourses] = useState([])
  const [sessions, setSessions] = useState([])
  const [insights, setInsights] = useState({
    has_data: false,
    weaknesses: [],
    strengths: [],
    developing: [],
    recommendations: [],
    coaching_note: '',
  })
  const [activeFilter, setActiveFilter] = useState('all')
  const [assessments, setAssessments] = useState([])
  const [assignments, setAssignments] = useState([])
  const [showReportModal, setShowReportModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let isMounted = true

    async function loadStudentData() {
      setLoading(true)
      setError('')
      try {
        const [coursesRes, sessionsRes, insightsRes, assessmentsRes, assignmentsRes] = await Promise.all([
          apiClient.get('/api/courses'),
          apiClient.get('/api/viva/sessions'),
          apiClient.get('/api/viva/insights'),
          apiClient.get('/api/student/assessments').catch(() => ({ data: [] })),
          apiClient.get('/api/student/assignments').catch(() => ({ data: [] })),
        ])
        if (isMounted) {
          setCourses(Array.isArray(coursesRes.data) ? coursesRes.data : [])
          setSessions(Array.isArray(sessionsRes.data) ? sessionsRes.data : [])
          setInsights(insightsRes.data || {})
          setAssessments(Array.isArray(assessmentsRes.data) ? assessmentsRes.data : [])
          setAssignments(Array.isArray(assignmentsRes.data) ? assignmentsRes.data : [])
        }
      } catch (err) {
        if (isMounted) {
          setError(err.userMessage || 'Could not load your workspace.')
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadStudentData()
    return () => {
      isMounted = false
    }
  }, [])

  const startPractice = (courseId, topicId) => {
    if (courseId) {
      navigate(buildPracticeUrl(courseId, topicId))
    }
  }

  const firstName = user?.full_name ? user.full_name.trim().split(' ')[0] : 'there'
  const stats = calculateStudentStats(sessions)
  const filteredSessions = filterStudentSessions(sessions, activeFilter)
  const scoreTrend = getRecentScoreTrend(sessions, 4)

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">STUDENT WORKSPACE</p>
          <h1>{getStudentDashboardGreeting(user?.full_name, sessions.length)}</h1>
          <p className="muted">Choose a course and get comfortable explaining what you know.</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="button secondary"
            onClick={() => setShowReportModal(true)}
          >
            📊 Detailed Performance Report
          </button>
          <button
            className="button primary"
            disabled={loading || courses.length === 0}
            onClick={() => startPractice(courses[0]?.id)}
          >
            Start a practice viva <span aria-hidden="true">↗</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="notice error-text" role="alert" style={{ marginBottom: '24px' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p className="muted">Loading your courses, performance insights, and practice records…</p>
      ) : (
        <>
          {/* Adaptive AI Viva Practice Hero Card */}
          <section className="adaptive-practice-hero" style={{ marginBottom: '32px', padding: '22px 24px', background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95))', borderRadius: '14px', border: '1px solid rgba(255, 255, 255, 0.1)', boxShadow: '0 8px 24px rgba(0,0,0,0.15)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
              <div style={{ maxWidth: '640px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <span style={{ fontSize: '1.25rem' }}>🎯</span>
                  <span className="eyebrow" style={{ color: '#bc603e', margin: 0 }}>ADAPTIVE AI VIVA</span>
                </div>
                <h2 style={{ fontSize: '1.35rem', margin: '0 0 8px 0', color: '#faf8f5' }}>
                  Practice with Real-Time Adaptive Questioning
                </h2>
                <p style={{ margin: '0 0 16px 0', fontSize: '0.95rem', color: '#77808a', lineHeight: 1.5 }}>
                  The oral exam engine actively monitors your answers in real time: strong responses smoothly escalate question difficulty, while struggles automatically introduce foundational concepts to solidify your understanding.
                </p>
                {insights?.weaknesses?.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.85rem', color: '#e9e7e2', fontWeight: 600 }}>Recommended Focus Areas:</span>
                    {insights.weaknesses.slice(0, 3).map((w) => (
                      <button
                        key={w.topic_id}
                        className="button secondary small"
                        style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                        onClick={() => navigate(buildAdaptivePracticeUrl(w.course_id, w.topic_id))}
                        title={`Practice ${w.topic_name}`}
                      >
                        ⚡ Focus on {w.topic_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  className="button primary"
                  disabled={loading || courses.length === 0}
                  onClick={() => navigate(buildAdaptivePracticeUrl(courses[0]?.id))}
                  style={{ minWidth: '200px' }}
                >
                  🎯 Start Adaptive Viva <span aria-hidden="true">↗</span>
                </button>
                <button
                  className="button secondary"
                  onClick={() => setShowReportModal(true)}
                  style={{ minWidth: '200px' }}
                >
                  📊 Performance Report
                </button>
              </div>
            </div>
          </section>

          {/* Performance Overview & Learning Summary */}
          <section aria-label="Performance overview" style={{ marginBottom: '40px' }}>
            <div className="stats-grid">
              <article className="stat-card">
                <span className="stat-label">Completed Vivas</span>
                <strong className="stat-value">{stats.completedCount}</strong>
                <span className="muted" style={{ fontSize: '12px' }}>
                  {stats.totalAttempted === 0
                    ? 'No viva attempts yet'
                    : `Out of ${stats.totalAttempted} attempted`}
                </span>
              </article>

              <article className="stat-card">
                <span className="stat-label">Average Score</span>
                <strong className="stat-value">{stats.averageScorePercent}</strong>
                <div className="score-track" aria-hidden="true">
                  <i style={{ width: `${Math.round(stats.averageScoreRatio * 100)}%` }} />
                </div>
                <span className="muted" style={{ fontSize: '12px', marginTop: '6px' }}>
                  {stats.scoredCount === 0
                    ? 'Awaiting completed reviews'
                    : `Based on ${stats.scoredCount} evaluated ${stats.scoredCount === 1 ? 'viva' : 'vivas'}`}
                </span>
              </article>

              <article className="stat-card">
                <span className="stat-label">In Progress</span>
                <strong className="stat-value">{stats.inProgressCount}</strong>
                <span className="muted" style={{ fontSize: '12px' }}>
                  {stats.inProgressCount === 0
                    ? 'All started vivas completed'
                    : 'Active practice sessions'}
                </span>
              </article>
            </div>

            {scoreTrend.length > 0 && (
              <div style={{ marginTop: '-20px', marginBottom: '28px' }}>
                <span className="muted" style={{ fontSize: '12px', fontWeight: 600 }}>
                  Recent scores:
                </span>
                <div className="trend-strip">
                  {scoreTrend.map((item) => (
                    <div className="trend-item" key={item.id}>
                      <span>{item.courseName}:</span>
                      <strong>{item.scorePercent}</strong>
                      <span className="muted" style={{ fontSize: '11px' }}>({item.date})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* AI-Powered Student Learning Insights & Recommendations */}
          <section aria-label="AI learning insights" style={{ marginBottom: '52px' }}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">AI LEARNING DIAGNOSTICS</p>
                <h2>Personalized Insights & Recommended Practice</h2>
              </div>
              <span className="count-pill">
                {insights.has_data
                  ? `${insights.total_evaluated_answers} answers analyzed`
                  : 'Diagnostic preview'}
              </span>
            </div>

            {/* Coaching Guidance Banner */}
            {insights.coaching_note && (
              <div className="coaching-box" role="status">
                <span className="coaching-icon" aria-hidden="true">💡</span>
                <div>
                  <strong style={{ display: 'block', fontSize: '14px', marginBottom: '4px' }}>
                    Personalized Coaching Focus
                  </strong>
                  <p style={{ margin: 0, fontSize: '13px', color: '#525a61' }}>
                    {insights.coaching_note}
                  </p>
                </div>
              </div>
            )}

            {/* Recommended Next Practice Sessions */}
            {insights.recommendations && insights.recommendations.length > 0 && (
              <div style={{ marginBottom: '32px' }}>
                <h3 style={{ fontSize: '16px', marginBottom: '12px', color: 'var(--ink)' }}>
                  Recommended Practice Topics
                </h3>
                <div className="recommendation-list">
                  {insights.recommendations.map((rec) => (
                    <div className="recommendation-item" key={rec.id}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <strong>{rec.topic_name}</strong>
                          <span className="course-code">{rec.course_code || rec.course_name}</span>
                          <span
                            className="count-pill"
                            style={{
                              fontSize: '11px',
                              background: rec.priority === 'high' ? '#faeceb' : '#f0eee9',
                              color: rec.priority === 'high' ? '#a54439' : '#6d716f',
                              fontWeight: 700,
                            }}
                          >
                            {rec.priority === 'high' ? 'High Focus' : 'Recommended'}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted)' }}>
                          {rec.reason}
                        </p>
                      </div>
                      <button
                        className="button primary"
                        style={{ padding: '8px 14px', fontSize: '13px', whiteSpace: 'nowrap' }}
                        onClick={() => navigate(rec.start_url || buildPracticeUrl(rec.course_id, rec.topic_id))}
                      >
                        Practice Topic ↗
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Identified Conceptual Weaknesses vs Strengths */}
            {insights.has_data ? (
              <div className="insights-grid">
                {/* Weaknesses Card */}
                <article className="insight-box weakness">
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <p className="eyebrow" style={{ color: '#a54439', margin: 0 }}>TOPICS NEEDING PRACTICE</p>
                      <span className="count-pill" style={{ background: '#faeceb', color: '#a54439' }}>
                        {insights.weaknesses.length} {insights.weaknesses.length === 1 ? 'gap' : 'gaps'}
                      </span>
                    </div>
                    <h3 style={{ fontSize: '18px', margin: '4px 0 10px' }}>Conceptual Focus Areas</h3>

                    {insights.weaknesses.length ? (
                      <div style={{ display: 'grid', gap: '14px', marginTop: '12px' }}>
                        {insights.weaknesses.map((w) => (
                          <div
                            key={w.topic_id}
                            style={{
                              background: '#fcfbf9',
                              border: '1px solid var(--line)',
                              borderRadius: '7px',
                              padding: '12px 14px',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <strong style={{ fontSize: '14px' }}>{w.topic_name}</strong>
                              <span style={{ fontWeight: 700, color: '#a54439', fontSize: '13px' }}>
                                {w.average_score_percent}
                              </span>
                            </div>
                            <span className="muted" style={{ fontSize: '11px' }}>
                              {w.course_name} · {w.evaluated_answers_count} evaluated {w.evaluated_answers_count === 1 ? 'question' : 'questions'}
                            </span>
                            <div className="dimension-pills">
                              <span className="dimension-pill">
                                {formatDimensionSummary(w.dimension_scores)}
                              </span>
                            </div>
                            {w.feedback_themes && w.feedback_themes.length > 0 && (
                              <p style={{ margin: '6px 0 8px', fontSize: '12px', color: '#656d73' }}>
                                &ldquo;{w.feedback_themes[0]}&rdquo;
                              </p>
                            )}
                            <button
                              className="text-button"
                              style={{ fontSize: '12px' }}
                              onClick={() => startPractice(w.course_id, w.topic_id)}
                            >
                              Practice this topic →
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="muted" style={{ fontSize: '13px', margin: '12px 0 0' }}>
                        No significant conceptual weaknesses detected! Your evaluated topics meet or exceed proficiency thresholds.
                      </p>
                    )}
                  </div>
                </article>

                {/* Strengths Card */}
                <article className="insight-box strength">
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <p className="eyebrow" style={{ color: '#41765f', margin: 0 }}>DEMONSTRATED MASTERY</p>
                      <span className="count-pill" style={{ background: '#edf4ee', color: '#41765f' }}>
                        {insights.strengths.length} {insights.strengths.length === 1 ? 'strength' : 'strengths'}
                      </span>
                    </div>
                    <h3 style={{ fontSize: '18px', margin: '4px 0 10px' }}>Strong Topics</h3>

                    {insights.strengths.length ? (
                      <div style={{ display: 'grid', gap: '14px', marginTop: '12px' }}>
                        {insights.strengths.map((s) => (
                          <div
                            key={s.topic_id}
                            style={{
                              background: '#fcfbf9',
                              border: '1px solid var(--line)',
                              borderRadius: '7px',
                              padding: '12px 14px',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <strong style={{ fontSize: '14px' }}>{s.topic_name}</strong>
                              <span style={{ fontWeight: 700, color: '#41765f', fontSize: '13px' }}>
                                {s.average_score_percent}
                              </span>
                            </div>
                            <span className="muted" style={{ fontSize: '11px' }}>
                              {s.course_name} · {s.evaluated_answers_count} evaluated {s.evaluated_answers_count === 1 ? 'question' : 'questions'}
                            </span>
                            <div className="dimension-pills">
                              <span className="dimension-pill">
                                {formatDimensionSummary(s.dimension_scores)}
                              </span>
                            </div>
                            {s.feedback_themes && s.feedback_themes.length > 0 && (
                              <p style={{ margin: '6px 0 0', fontSize: '12px', color: '#656d73' }}>
                                &ldquo;{s.feedback_themes[0]}&rdquo;
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="muted" style={{ fontSize: '13px', margin: '12px 0 0' }}>
                        Keep completing viva sessions. Once topics achieve an average of 80% or higher, they will appear here as demonstrated strengths.
                      </p>
                    )}
                  </div>
                </article>
              </div>
            ) : (
              <div className="empty-state" style={{ marginBottom: '24px' }}>
                <h3>Complete your first viva to unlock learning diagnostics</h3>
                <p>
                  As you answer oral questions, Parakh AI evaluates your conceptual accuracy, completeness, and clarity to detect weaknesses and tailor practice sessions.
                </p>
              </div>
            )}
          </section>

          {/* Scheduled & Custom Oral Exams */}
          {assessments && assessments.length > 0 && (
            <section aria-label="Assigned oral assessments" style={{ marginBottom: '36px' }}>
              <div className="section-heading">
                <div>
                  <p className="eyebrow" style={{ color: 'var(--accent-dark)' }}>EXAMINATION STUDIO</p>
                  <h2>Scheduled &amp; Custom Oral Exams</h2>
                </div>
                <span className="count-pill">
                  {assessments.length} {assessments.length === 1 ? 'assessment' : 'assessments'}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
                {assessments.map((a) => (
                  <article
                    key={a.id}
                    style={{
                      background: '#fff',
                      border: '1px solid var(--line)',
                      borderRadius: '10px',
                      padding: '20px 22px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      boxShadow: 'var(--shadow-sm)',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                        <div>
                          <span className="course-code" style={{ marginBottom: '4px', display: 'inline-block' }}>
                            {a.course_code || a.course_name}
                          </span>
                          <h3 style={{ margin: '2px 0 6px', fontSize: '17px', color: 'var(--heading)' }}>
                            {a.title}
                          </h3>
                        </div>
                        <span
                          className="status-tag"
                          style={{
                            textTransform: 'capitalize',
                            background: a.difficulty === 'hard' ? '#fae8e5' : a.difficulty === 'easy' ? '#e8f3ee' : '#faf1e4',
                            color: a.difficulty === 'hard' ? '#a54439' : a.difficulty === 'easy' ? '#41765f' : '#b27a31',
                          }}
                        >
                          {a.difficulty}
                        </span>
                      </div>

                      {a.description && (
                        <p style={{ margin: '6px 0 10px', fontSize: '13px', color: 'var(--muted)' }}>
                          {a.description}
                        </p>
                      )}

                      <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: '#77808a', margin: '8px 0 12px' }}>
                        <span>⏱ {a.duration_minutes} mins</span>
                        <span>·</span>
                        <span>📝 {a.question_count} questions</span>
                        {a.user_attempts_count > 0 && (
                          <>
                            <span>·</span>
                            <span style={{ color: '#41765f', fontWeight: 600 }}>
                              {a.user_attempts_count} attempt{a.user_attempts_count === 1 ? '' : 's'} (Best: {a.latest_score_percent})
                            </span>
                          </>
                        )}
                      </div>

                      {a.instructions && (
                        <p style={{ fontSize: '12px', background: '#faf8f5', padding: '8px 10px', borderRadius: '6px', color: '#77808a', margin: '0 0 16px' }}>
                          ℹ️ {a.instructions}
                        </p>
                      )}
                    </div>

                    <button
                      className="button primary"
                      style={{ width: '100%', marginTop: '8px' }}
                      onClick={() => navigate(a.start_url)}
                    >
                      {a.user_attempts_count > 0 ? 'Retake Oral Exam ↗' : 'Start Oral Exam ↗'}
                    </button>
                  </article>
                ))}
              </div>
            </section>
          )}

          {/* Assignments & Deadlines Section */}
          <section aria-label="Assigned oral assessments with deadlines" style={{ marginBottom: '36px' }}>
            <div className="section-heading">
              <div>
                <p className="eyebrow" style={{ color: 'var(--accent-dark)' }}>SCHEDULED EXAMINATIONS</p>
                <h2>Your Assignments &amp; Deadlines</h2>
              </div>
              <span className="count-pill">
                {assignments.length} {assignments.length === 1 ? 'assignment' : 'assignments'}
              </span>
            </div>

            {assignments.length === 0 ? (
              <div className="empty-state" style={{ marginBottom: '16px' }}>
                <h3>No assignments scheduled</h3>
                <p>You have no pending scheduled oral assessments from your instructors at this time.</p>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
                {assignments.map((a) => {
                  const statusMeta = formatAssignmentStatus(a.status)
                  return (
                    <article
                      key={a.id}
                      style={{
                        background: '#fff',
                        border: '1px solid var(--line)',
                        borderRadius: '10px',
                        padding: '20px 22px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        boxShadow: 'var(--shadow-sm)',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                          <div>
                            <span className="course-code" style={{ marginBottom: '4px', display: 'inline-block' }}>
                              {a.course_code || a.course_name}
                            </span>
                            <h3 style={{ margin: '2px 0 6px', fontSize: '17px', color: 'var(--heading)' }}>
                              {a.title}
                            </h3>
                          </div>
                          <span className={statusMeta.className}>
                            {statusMeta.label}
                          </span>
                        </div>

                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', fontSize: '12px', color: '#77808a', margin: '8px 0 12px' }}>
                          {a.duration_minutes && <span>⏱ {a.duration_minutes} mins</span>}
                          <span>🎯 Attempts: {a.attempts_used} / {a.attempt_limit}</span>
                          {a.latest_score !== null && a.latest_score !== undefined && (
                            <span style={{ color: '#41765f', fontWeight: 600 }}>
                              ⭐ Score: {formatRatioPercent(a.latest_score)}
                            </span>
                          )}
                        </div>

                        <div style={{ background: '#faf8f5', padding: '10px 12px', borderRadius: '6px', fontSize: '12px', color: '#77808a', margin: '0 0 14px' }}>
                          <div style={{ marginBottom: '4px' }}>
                            <strong>Opens:</strong> {formatAssignmentDate(a.start_date, 'Immediate')}
                          </div>
                          <div>
                            <strong>Deadline:</strong> {formatAssignmentDate(a.deadline, 'No strict deadline')}
                          </div>
                          {a.instructions && (
                            <div style={{ marginTop: '6px', borderTop: '1px dashed #e2ded9', paddingTop: '6px' }}>
                              ℹ️ {a.instructions}
                            </div>
                          )}
                        </div>
                      </div>

                      <div>
                        {a.can_launch && (
                          <button
                            className="button primary"
                            style={{ width: '100%' }}
                            onClick={() => navigate(`/viva/${a.course_id}?assignment=${a.id}`)}
                          >
                            Start Assessment ↗
                          </button>
                        )}
                        {a.status === 'submitted' && a.latest_session_id && (
                          <button
                            className="button secondary"
                            style={{ width: '100%' }}
                            onClick={() => navigate(`/report/${a.latest_session_id}`)}
                          >
                            View Feedback Report ↗
                          </button>
                        )}
                        {a.status === 'scheduled' && (
                          <button
                            className="button secondary"
                            disabled
                            style={{ width: '100%', opacity: 0.65, cursor: 'not-allowed' }}
                          >
                            Opens {formatAssignmentDate(a.start_date)}
                          </button>
                        )}
                        {a.status === 'overdue' && (
                          <button
                            className="button secondary"
                            disabled
                            style={{ width: '100%', opacity: 0.65, cursor: 'not-allowed' }}
                          >
                            Deadline Passed
                          </button>
                        )}
                        {a.status === 'closed' && (
                          <button
                            className="button secondary"
                            disabled
                            style={{ width: '100%', opacity: 0.65, cursor: 'not-allowed' }}
                          >
                            Assignment Closed
                          </button>
                        )}
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </section>

          {/* Available Courses & Topics */}
          <section aria-label="Available courses">
            <div className="section-heading">
              <div>
                <p className="eyebrow">YOUR LEARNING</p>
                <h2>Available courses</h2>
              </div>
              <span className="count-pill">
                {courses.length} {courses.length === 1 ? 'course' : 'courses'}
              </span>
            </div>

            {courses.length ? (
              <div className="course-grid">
                {courses.map((course, i) => (
                  <article className="course-card" key={course.id}>
                    <div className="course-art">
                      {String(i + 1).padStart(2, '0')}
                    </div>
                    <span className="course-code">{course.subject || course.code}</span>
                    <h3>{course.name}</h3>
                    <p>
                      {course.description ||
                        'Build confidence through a focused oral practice session.'}
                    </p>

                    {course.topics && course.topics.length > 0 && (
                      <div className="course-topics-preview">
                        {course.topics.slice(0, 3).map((topic) => (
                          <span className="course-topic-tag" key={topic.id || topic.name}>
                            {topic.name}
                          </span>
                        ))}
                        {course.topics.length > 3 && (
                          <span className="course-topic-tag">
                            +{course.topics.length - 3} more
                          </span>
                        )}
                      </div>
                    )}

                    <div className="course-bottom">
                      <span>{course.topics?.length || 0} topics</span>
                      <button
                        className="text-button"
                        onClick={() => startPractice(course.id)}
                      >
                        Start Practice <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>No courses available yet</h3>
                <p>Ask your teacher to add course material before starting a viva.</p>
              </div>
            )}
          </section>

          {/* Viva History & Practice Records */}
          <section className="recent-section" aria-label="Viva practice history">
            <div className="section-heading">
              <div>
                <p className="eyebrow">KEEP YOUR MOMENTUM</p>
                <h2>Viva practice history</h2>
              </div>
            </div>

            {sessions.length > 0 && (
              <div className="filter-tabs" role="tablist" aria-label="Filter sessions">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeFilter === 'all'}
                  className={`filter-tab ${activeFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setActiveFilter('all')}
                >
                  All ({stats.totalAttempted})
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeFilter === 'completed'}
                  className={`filter-tab ${activeFilter === 'completed' ? 'active' : ''}`}
                  onClick={() => setActiveFilter('completed')}
                >
                  Completed ({stats.completedCount})
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeFilter === 'in_progress'}
                  className={`filter-tab ${activeFilter === 'in_progress' ? 'active' : ''}`}
                  onClick={() => setActiveFilter('in_progress')}
                >
                  In Progress ({stats.inProgressCount})
                </button>
              </div>
            )}

            {sessions.length === 0 ? (
              <div className="empty-state">
                <h3>No practice sessions yet</h3>
                <p>
                  Choose an available course above to start your first oral practice session.
                </p>
              </div>
            ) : filteredSessions.length === 0 ? (
              <div className="empty-state">
                <p>No practice sessions match the selected filter.</p>
              </div>
            ) : (
              <div className="session-list">
                {filteredSessions.map((s) => (
                  <div className="session-row" key={s.id}>
                    <div>
                      <strong>
                        {s.course_name || s.course_code || 'Practice session'}
                      </strong>
                      <span>
                        {formatSessionDate(s.finished_at || s.created_at || s.started_at)} ·{' '}
                        {s.max_questions ? `${s.max_questions} questions` : 'Oral session'}
                      </span>
                    </div>

                    <span
                      className={`status-tag ${
                        s.status === 'completed' ? 'completed' : 'in_progress'
                      }`}
                    >
                      {s.status.replace('_', ' ')}
                    </span>

                    {s.status === 'completed' && (
                      <span className="session-score">
                        {formatRatioPercent(s.total_score)}
                      </span>
                    )}

                    {s.status === 'completed' ? (
                      <button
                        className="text-button"
                        onClick={() => navigate(`/report/${s.id}`)}
                      >
                        View report →
                      </button>
                    ) : (
                      <button
                        className="text-button"
                        onClick={() => startPractice(s.course_id)}
                      >
                        Practice again →
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
          {showReportModal && (
        <StudentPerformanceReportModal
          onClose={() => setShowReportModal(false)}
          onNavigate={navigate}
        />
      )}
    </main>
  )
}
