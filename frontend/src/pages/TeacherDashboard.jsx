import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import { formatRatioPercent } from '../utils/formatters'
import { formatSessionDate } from '../utils/studentProgressHelpers'
import {
  calculateScoreDistribution,
  filterSessionsByDateRange,
  filterStudents,
  getStudentScoreProgress,
} from '../utils/teacherAnalyticsHelpers'
import CustomVivaBuilder from '../components/CustomVivaBuilder'
import AssignmentManager from '../components/AssignmentManager'
import TeacherReportsManager from '../components/TeacherReportsManager'
import QuestionBank from './QuestionBank'
import DocumentManager from '../components/DocumentManager'
import '../teacher-tools.css'

const blankCourse = {
  name: '',
  subject: '',
  code: '',
  academic_level: '',
  description: '',
  syllabus_text: '',
  interview_config: {
    max_questions: 5,
    max_duration_sec: 900,
    difficulty: 'medium',
    topic_ids: [],
  },
}

export default function TeacherDashboard({ navigate }) {
  const [activeTab, setActiveTab] = useState('analytics')
  const [courses, setCourses] = useState([])
  const [sessions, setSessions] = useState([])
  const [analytics, setAnalytics] = useState({
    summary: {
      total_students: 0,
      total_sessions: 0,
      completed_sessions: 0,
      in_progress_sessions: 0,
      average_score: null,
      average_score_percent: '—',
    },
    students: [],
    courses: [],
    topics: [],
    class_weaknesses: [],
    recent_activity: [],
  })

  // Filters & selection
  const [selectedCourseFilter, setSelectedCourseFilter] = useState('')
  const [dateRangeFilter, setDateRangeFilter] = useState('all')
  const [studentSearch, setStudentSearch] = useState('')
  const [selectedStudent, setSelectedStudent] = useState(null)

  // Course Editor states
  const [selectedCourseId, setSelectedCourseId] = useState('')
  const [courseForm, setCourseForm] = useState(blankCourse)
  const [topicDrafts, setTopicDrafts] = useState({})

  // Feedback states
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const loadData = async (courseId = '', { silent = false } = {}) => {
    if (!silent) setLoading(true)
    setError('')
    try {
      const params = courseId ? { course_id: courseId } : {}
      const [analyticsRes, sessionsRes, coursesRes] = await Promise.all([
        apiClient.get('/api/teacher/analytics', { params }),
        apiClient.get('/api/teacher/sessions', { params }),
        apiClient.get('/api/courses'),
      ])
      setAnalytics(analyticsRes.data)
      setSessions(Array.isArray(sessionsRes.data) ? sessionsRes.data : [])
      setCourses(Array.isArray(coursesRes.data) ? coursesRes.data : [])
    } catch (cause) {
      setError(cause.userMessage || 'Could not load teacher analytics and course data.')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    loadData(selectedCourseFilter)
  }, [selectedCourseFilter])

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId),
    [courses, selectedCourseId],
  )

  const dateFilteredSessions = useMemo(() => {
    return filterSessionsByDateRange(sessions, dateRangeFilter)
  }, [sessions, dateRangeFilter])

  const scoreDist = useMemo(() => {
    return calculateScoreDistribution(dateFilteredSessions)
  }, [dateFilteredSessions])

  const filteredStudentsList = useMemo(() => {
    return filterStudents(analytics.students || [], studentSearch)
  }, [analytics.students, studentSearch])

  const studentTrend = useMemo(() => {
    if (!selectedStudent || !selectedStudent.sessions) return null
    return getStudentScoreProgress(selectedStudent.sessions)
  }, [selectedStudent])

  const exportCsv = async () => {
    try {
      const { data } = await apiClient.get('/api/reports/export', {
        params: { course_id: selectedCourseFilter || undefined },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(data)
      const link = document.createElement('a')
      link.href = url
      link.download = 'viva-sessions.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause.userMessage || 'CSV export is unavailable.')
    }
  }

  // Course Management handlers
  const openCourse = (id) => {
    setSelectedCourseId(id)
    setNotice('')
    setError('')
    if (!id) {
      setCourseForm(blankCourse)
      setTopicDrafts({})
      return
    }
    const course = courses.find((item) => item.id === id)
    if (!course) return
    setCourseForm({
      name: course.name,
      subject: course.subject || '',
      code: course.code,
      academic_level: course.academic_level || '',
      description: course.description || '',
      syllabus_text: course.syllabus_text || '',
      interview_config: {
        max_questions: course.interview_config?.max_questions || 5,
        max_duration_sec: course.interview_config?.max_duration_sec || 900,
        difficulty: course.interview_config?.difficulty || 'medium',
        topic_ids: course.interview_config?.topic_ids || [],
      },
    })
    setTopicDrafts(Object.fromEntries((course.topics || []).map((topic) => [topic.id, topic.name])))
  }

  const saveCourse = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = selectedCourseId
        ? await apiClient.put(`/api/courses/${selectedCourseId}`, courseForm)
        : await apiClient.post('/api/courses', courseForm)
      const saved = response.data
      setCourses((existing) => [
        saved,
        ...existing.filter((course) => course.id !== saved.id),
      ])
      setSelectedCourseId(saved.id)
      setNotice('Course and syllabus saved.')
    } catch (cause) {
      setError(cause.userMessage || 'Could not save this course.')
    } finally {
      setSaving(false)
    }
  }

  const analyzeSyllabus = async () => {
    if (!selectedCourseId) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { data } = await apiClient.post(`/api/courses/${selectedCourseId}/syllabus/analyze`)
      setCourses((existing) => existing.map((course) => (course.id === data.id ? data : course)))
      setTopicDrafts(Object.fromEntries((data.topics || []).map((topic) => [topic.id, topic.name])))
      setNotice('Syllabus analyzed. Review the extracted topics below before interviews.')
    } catch (cause) {
      setError(cause.userMessage || 'Syllabus analysis failed.')
    } finally {
      setSaving(false)
    }
  }

  const saveTopicName = async (topic) => {
    const name = (topicDrafts[topic.id] || '').trim()
    if (!name) {
      setError('A topic name cannot be empty.')
      return
    }
    setError('')
    try {
      const { data } = await apiClient.put(
        `/api/courses/${selectedCourseId}/syllabus/topics/${topic.id}`,
        { name },
      )
      setCourses((existing) => existing.map((course) => (course.id === data.id ? data : course)))
      setTopicDrafts(Object.fromEntries((data.topics || []).map((item) => [item.id, item.name])))
      setNotice('Syllabus topic updated.')
    } catch (cause) {
      setError(cause.userMessage || 'Could not update the topic.')
    }
  }

  const setInterviewConfig = (key, value) => {
    setCourseForm((current) => ({
      ...current,
      interview_config: { ...current.interview_config, [key]: value },
    }))
  }

  const toggleInterviewTopic = (topicId) => {
    const selected = courseForm.interview_config.topic_ids || []
    setInterviewConfig(
      'topic_ids',
      selected.includes(topicId) ? selected.filter((id) => id !== topicId) : [...selected, topicId],
    )
  }

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">TEACHER WORKSPACE</p>
          <h1>Class Performance & Teaching Studio</h1>
          <p className="muted">
            Monitor oral exam progress, review individual students, configure syllabi, and calibrate viva evaluation.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="button secondary" onClick={exportCsv}>
            ↓ Export CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="error-text notice" role="alert" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}
      {notice && (
        <div className="success-text notice" role="status" style={{ marginBottom: '20px' }}>
          {notice}
        </div>
      )}

      {/* Top Workspace Navigation Tabs */}
      <div className="filter-tabs" role="tablist" aria-label="Teacher workspace views" style={{ marginBottom: '32px' }}>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'analytics'}
          className={`filter-tab ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          📊 Class Insights
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'students'}
          className={`filter-tab ${activeTab === 'students' ? 'active' : ''}`}
          onClick={() => setActiveTab('students')}
        >
          👥 Students ({analytics.summary.total_students})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'courses'}
          className={`filter-tab ${activeTab === 'courses' ? 'active' : ''}`}
          onClick={() => setActiveTab('courses')}
        >
          📚 Courses & Syllabus ({courses.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'sessions'}
          className={`filter-tab ${activeTab === 'sessions' ? 'active' : ''}`}
          onClick={() => setActiveTab('sessions')}
        >
          📝 Review Sessions ({sessions.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'builder'}
          className={`filter-tab ${activeTab === 'builder' ? 'active' : ''}`}
          onClick={() => setActiveTab('builder')}
        >
          🛠️ Custom Viva Builder
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'questions'}
          className={`filter-tab ${activeTab === 'questions' ? 'active' : ''}`}
          onClick={() => setActiveTab('questions')}
        >
          ❓ Question Bank
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'assignments'}
          className={`filter-tab ${activeTab === 'assignments' ? 'active' : ''}`}
          onClick={() => setActiveTab('assignments')}
        >
          📅 Assignments & Deadlines
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'reports'}
          className={`filter-tab ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          📊 Reports &amp; Export
        </button>
      </div>

      {loading ? (
        <p className="muted">Loading class analytics and records…</p>
      ) : (
        <>
          {/* TAB 1: CLASS ANALYTICS & INSIGHTS */}
          {activeTab === 'analytics' && (
            <section aria-label="Class analytics and insights">
              {/* Filter controls */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '16px',
                  marginBottom: '24px',
                  background: '#fff',
                  border: '1px solid var(--line)',
                  borderRadius: '10px',
                  padding: '16px 20px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <label className="filter-label" style={{ fontWeight: 600 }}>
                    Course filter:
                    <select
                      value={selectedCourseFilter}
                      onChange={(e) => setSelectedCourseFilter(e.target.value)}
                    >
                      <option value="">All My Courses</option>
                      {courses.map((c) => (
                        <option value={c.id} key={c.id}>
                          {c.name} ({c.code})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="muted" style={{ fontSize: '13px', fontWeight: 600 }}>
                    Date Range:
                  </span>
                  <button
                    type="button"
                    className={`filter-tab ${dateRangeFilter === 'all' ? 'active' : ''}`}
                    onClick={() => setDateRangeFilter('all')}
                  >
                    All Time
                  </button>
                  <button
                    type="button"
                    className={`filter-tab ${dateRangeFilter === '30d' ? 'active' : ''}`}
                    onClick={() => setDateRangeFilter('30d')}
                  >
                    Last 30 Days
                  </button>
                  <button
                    type="button"
                    className={`filter-tab ${dateRangeFilter === '7d' ? 'active' : ''}`}
                    onClick={() => setDateRangeFilter('7d')}
                  >
                    Last 7 Days
                  </button>
                </div>
              </div>

              {/* 4 Key Metric Cards */}
              <div className="stats-grid">
                <article className="stat-card">
                  <span className="stat-label">Accessible Students</span>
                  <strong className="stat-value">{analytics.summary.total_students}</strong>
                  <span className="muted" style={{ fontSize: '12px' }}>
                    {analytics.summary.total_students === 1 ? '1 student participated' : `${analytics.summary.total_students} students participated`}
                  </span>
                </article>

                <article className="stat-card">
                  <span className="stat-label">Total Viva Sessions</span>
                  <strong className="stat-value">{analytics.summary.total_sessions}</strong>
                  <span className="muted" style={{ fontSize: '12px' }}>
                    {analytics.summary.completed_sessions} completed · {analytics.summary.in_progress_sessions} in progress
                  </span>
                </article>

                <article className="stat-card">
                  <span className="stat-label">Class Average Score</span>
                  <strong className="stat-value">{analytics.summary.average_score_percent}</strong>
                  <div className="score-track" aria-hidden="true">
                    <i
                      style={{
                        width: `${
                          analytics.summary.average_score !== null
                            ? Math.round(analytics.summary.average_score * 100)
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <span className="muted" style={{ fontSize: '12px', marginTop: '6px' }}>
                    {analytics.summary.average_score !== null
                      ? 'Calculated from valid scored sessions'
                      : 'No scored sessions yet'}
                  </span>
                </article>

                <article className="stat-card">
                  <span className="stat-label">Configured Courses</span>
                  <strong className="stat-value">{courses.length}</strong>
                  <span className="muted" style={{ fontSize: '12px' }}>
                    Active oral exam curricula
                  </span>
                </article>
              </div>

              {/* Performance Distribution Tier */}
              {scoreDist.totalScored > 0 && (
                <div className="table-card" style={{ marginBottom: '32px' }}>
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">SCORE TIERS</p>
                      <h2>Performance Distribution</h2>
                    </div>
                    <span className="count-pill">{scoreDist.totalScored} scored sessions</span>
                  </div>
                  <div className="dist-bar" aria-label="Score tier distribution">
                    <div
                      className="dist-seg-mastery"
                      style={{ width: `${(scoreDist.mastery / scoreDist.totalScored) * 100}%` }}
                      title={`Mastery (85-100%): ${scoreDist.mastery}`}
                    />
                    <div
                      className="dist-seg-proficient"
                      style={{ width: `${(scoreDist.proficient / scoreDist.totalScored) * 100}%` }}
                      title={`Proficient (70-84%): ${scoreDist.proficient}`}
                    />
                    <div
                      className="dist-seg-developing"
                      style={{ width: `${(scoreDist.developing / scoreDist.totalScored) * 100}%` }}
                      title={`Developing (50-69%): ${scoreDist.developing}`}
                    />
                    <div
                      className="dist-seg-attention"
                      style={{ width: `${(scoreDist.needsAttention / scoreDist.totalScored) * 100}%` }}
                      title={`Needs Attention (<50%): ${scoreDist.needsAttention}`}
                    />
                  </div>
                  <div className="dist-legend">
                    <span className="dist-legend-item">
                      <i className="dist-legend-dot" style={{ background: '#41765f' }} />
                      Mastery (85-100%): {scoreDist.mastery}
                    </span>
                    <span className="dist-legend-item">
                      <i className="dist-legend-dot" style={{ background: '#719b88' }} />
                      Proficient (70-84%): {scoreDist.proficient}
                    </span>
                    <span className="dist-legend-item">
                      <i className="dist-legend-dot" style={{ background: '#d49547' }} />
                      Developing (50-69%): {scoreDist.developing}
                    </span>
                    <span className="dist-legend-item">
                      <i className="dist-legend-dot" style={{ background: '#a54439' }} />
                      Needs Attention (&lt;50%): {scoreDist.needsAttention}
                    </span>
                  </div>
                </div>
              )}

              {/* Course-wise Performance & Participation */}
              <div className="table-card" style={{ marginBottom: '32px' }}>
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">COURSE BREAKDOWN</p>
                    <h2>Course-wise Performance & Participation</h2>
                  </div>
                </div>

                {analytics.courses.length ? (
                  <table className="analytics-table">
                    <thead>
                      <tr>
                        <th>Course</th>
                        <th>Code</th>
                        <th>Sessions</th>
                        <th>Completed</th>
                        <th>Students</th>
                        <th>Average Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.courses.map((c) => (
                        <tr key={c.course_id}>
                          <td>
                            <strong>{c.course_name}</strong>
                          </td>
                          <td>
                            <span className="course-code" style={{ letterSpacing: '0.5px' }}>
                              {c.course_code}
                            </span>
                          </td>
                          <td>{c.total_sessions}</td>
                          <td>{c.completed_sessions}</td>
                          <td>{c.student_count}</td>
                          <td>
                            <strong style={{ color: 'var(--accent-dark)' }}>
                              {c.average_score_percent}
                            </strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-state">
                    <h3>No courses created yet</h3>
                    <p>Create a course in the Courses & Syllabus tab to begin oral examinations.</p>
                  </div>
                )}
              </div>

              {/* Class-wide Weaknesses & Curriculum Gaps */}
              <div className="table-card" style={{ marginBottom: '32px' }}>
                <div className="section-heading">
                  <div>
                    <p className="eyebrow" style={{ color: '#a54439' }}>DIAGNOSTIC ALERTS</p>
                    <h2>Class-wide Weaknesses &amp; Curriculum Gaps</h2>
                  </div>
                  <span
                    className="count-pill"
                    style={{
                      background: (analytics.class_weaknesses || []).length ? '#fae8e5' : '#ebe6de',
                      color: (analytics.class_weaknesses || []).length ? '#a54439' : 'inherit',
                      fontWeight: 700,
                    }}
                  >
                    {(analytics.class_weaknesses || []).length}{' '}
                    {(analytics.class_weaknesses || []).length === 1 ? 'topic needs attention' : 'topics need attention'}
                  </span>
                </div>

                {(analytics.class_weaknesses && analytics.class_weaknesses.length > 0) ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
                    {analytics.class_weaknesses.map((w) => (
                      <article
                        key={w.topic_id}
                        style={{
                          background: '#fffdfa',
                          border: '1px solid #e8c9c5',
                          borderRadius: '10px',
                          padding: '16px 18px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '8px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                          <div>
                            <strong style={{ fontSize: '15px', color: '#252a30' }}>{w.topic_name}</strong>
                            <span className="muted" style={{ display: 'block', fontSize: '12px', marginTop: '2px' }}>
                              {w.course_name}
                            </span>
                          </div>
                          <span
                            className="badge"
                            style={{
                              background: '#fae8e5',
                              color: '#a54439',
                              border: '1px solid #f0b8b0',
                              padding: '3px 8px',
                              borderRadius: '6px',
                              fontSize: '12px',
                              fontWeight: 700,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Avg: {w.average_score_percent}
                          </span>
                        </div>

                        <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: '#77808a' }}>
                          <span>{w.student_count} {w.student_count === 1 ? 'student' : 'students'} evaluated</span>
                          <span>·</span>
                          <span>{w.attempt_count} {w.attempt_count === 1 ? 'attempt' : 'attempts'}</span>
                        </div>

                        {w.recommendation && (
                          <p style={{ margin: 0, fontSize: '12px', color: '#88352b', background: '#fdf2f0', padding: '6px 10px', borderRadius: '6px' }}>
                            💡 {w.recommendation}
                          </p>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state" style={{ padding: '24px 16px' }}>
                    <p className="muted" style={{ margin: 0, fontSize: '14px' }}>
                      No class-wide weaknesses identified. Topics with student performance below 65% will appear here with targeted review recommendations.
                    </p>
                  </div>
                )}
              </div>

              {/* Frequently Attempted Topics */}
              <div className="table-card" style={{ marginBottom: '32px' }}>
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">CURRICULUM COVERAGE</p>
                    <h2>Frequently Attempted Topics</h2>
                  </div>
                  <span className="count-pill">
                    {analytics.topics.length} {analytics.topics.length === 1 ? 'topic' : 'topics'}
                  </span>
                </div>

                {analytics.topics.length ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                    {analytics.topics.map((t) => (
                      <article
                        key={t.topic_id}
                        style={{
                          background: '#faf8f5',
                          border: '1px solid var(--line)',
                          borderRadius: '8px',
                          padding: '14px 16px',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <div>
                          <strong style={{ display: 'block', fontSize: '14px' }}>{t.topic_name}</strong>
                          <span className="muted" style={{ fontSize: '11px' }}>{t.course_name}</span>
                        </div>
                        <span className="count-pill" style={{ background: '#ebe6de', fontWeight: 700 }}>
                          {t.attempt_count} {t.attempt_count === 1 ? 'attempt' : 'attempts'}
                        </span>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <h3>No topic activity recorded yet</h3>
                    <p>As students answer viva questions in your courses, frequently tested topics will appear here.</p>
                  </div>
                )}
              </div>

              {/* Recent Student Activity */}
              <div className="table-card">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">LIVE PULSE</p>
                    <h2>Recent Student Activity</h2>
                  </div>
                </div>

                {analytics.recent_activity.length ? (
                  <div className="session-list">
                    {analytics.recent_activity.map((session) => (
                      <div className="session-row" key={session.id}>
                        <div>
                          <strong>{session.student_name}</strong>
                          <span>
                            {session.student_email && `${session.student_email} · `}
                            {session.course_name} · {formatSessionDate(session.created_at)}
                          </span>
                        </div>
                        <span className={`status-tag ${session.status}`}>
                          {session.status.replace('_', ' ')}
                        </span>
                        <span className="session-score">{session.total_score_percent}</span>
                        <button
                          className="text-button"
                          onClick={() => navigate(`/review/${session.id}`)}
                        >
                          Review →
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <h3>No viva sessions yet</h3>
                    <p>Once students start practicing in your courses, their sessions will appear here.</p>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* TAB 2: STUDENT PERFORMANCE */}
          {activeTab === 'students' && (
            <section aria-label="Student performance directory">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">CLASS DIRECTORY</p>
                  <h2>Student Performance & History</h2>
                </div>
                <label className="filter-label" style={{ maxWidth: '320px' }}>
                  <input
                    type="search"
                    placeholder="Search by student name or email…"
                    value={studentSearch}
                    onChange={(e) => setStudentSearch(e.target.value)}
                    style={{ width: '100%', padding: '9px 12px', border: '1px solid var(--line)', borderRadius: '6px' }}
                  />
                </label>
              </div>

              {filteredStudentsList.length ? (
                <div className="table-card">
                  <table className="analytics-table">
                    <thead>
                      <tr>
                        <th>Student Name</th>
                        <th>Email</th>
                        <th>Total Vivas</th>
                        <th>Completed</th>
                        <th>Average Score</th>
                        <th>Last Active</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredStudentsList.map((s) => (
                        <tr key={s.student_id}>
                          <td>
                            <strong>{s.student_name}</strong>
                          </td>
                          <td>
                            <span className="muted">{s.student_email || '—'}</span>
                          </td>
                          <td>{s.total_sessions}</td>
                          <td>{s.completed_sessions}</td>
                          <td>
                            <strong style={{ color: 'var(--accent-dark)' }}>
                              {s.average_score_percent}
                            </strong>
                          </td>
                          <td>
                            <span className="muted" style={{ fontSize: '12px' }}>
                              {formatSessionDate(s.last_active_at)}
                            </span>
                          </td>
                          <td>
                            <button
                              className="text-button"
                              onClick={() => setSelectedStudent(s)}
                            >
                              View History →
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">
                  <h3>No matching students found</h3>
                  <p>
                    {studentSearch
                      ? `No students match the search term "${studentSearch}".`
                      : 'Students will appear here as they take viva exams in your courses.'}
                  </p>
                </div>
              )}

              {/* Student Performance Drilldown Modal / Panel */}
              {selectedStudent && (
                <article className="student-drilldown" aria-label="Student details">
                  <div className="drilldown-header">
                    <div>
                      <p className="eyebrow">INDIVIDUAL PERFORMANCE RECORD</p>
                      <h2 style={{ margin: '4px 0 6px' }}>{selectedStudent.student_name}</h2>
                      <p className="muted" style={{ margin: 0, fontSize: '13px' }}>
                        {selectedStudent.student_email} · {selectedStudent.completed_sessions} completed out of{' '}
                        {selectedStudent.total_sessions} total viva sessions
                      </p>
                    </div>
                    <button
                      className="button secondary"
                      onClick={() => setSelectedStudent(null)}
                    >
                      ✕ Close History
                    </button>
                  </div>

                  {/* Score Trend */}
                  <div style={{ marginBottom: '24px' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
                      <span className="muted" style={{ fontSize: '13px', fontWeight: 700 }}>
                        Performance Trajectory:
                      </span>
                      {studentTrend?.hasTrend ? (
                        <span
                          className="count-pill"
                          style={{
                            background:
                              studentTrend.direction === 'up'
                                ? '#edf4ee'
                                : studentTrend.direction === 'down'
                                ? '#faeceb'
                                : '#f0eee9',
                            color:
                              studentTrend.direction === 'up'
                                ? '#50725b'
                                : studentTrend.direction === 'down'
                                ? '#a54439'
                                : '#6d716f',
                            fontWeight: 700,
                          }}
                        >
                          {studentTrend.deltaPercent} trajectory ({studentTrend.direction})
                        </span>
                      ) : (
                        <span className="muted" style={{ fontSize: '12px' }}>
                          Insufficient score history to display trend (at least 2 evaluated sessions required).
                        </span>
                      )}
                    </div>

                    {studentTrend?.hasTrend && (
                      <div className="trend-strip" style={{ marginTop: '10px' }}>
                        {studentTrend.progress.map((step, idx) => (
                          <div className="trend-item" key={step.id || idx}>
                            <span>Session {idx + 1}:</span>
                            <strong>{step.scorePercent}</strong>
                            <span className="muted" style={{ fontSize: '11px' }}>({step.date})</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Student Session History */}
                  <h3 style={{ fontSize: '16px', marginBottom: '12px' }}>Course Session History</h3>
                  <div className="session-list">
                    {selectedStudent.sessions.map((s) => (
                      <div className="session-row" key={s.id}>
                        <div>
                          <strong>{s.course_name || s.course_code || 'Oral Viva'}</strong>
                          <span>{formatSessionDate(s.created_at)}</span>
                        </div>
                        <span className={`status-tag ${s.status}`}>
                          {s.status.replace('_', ' ')}
                        </span>
                        <span className="session-score">{s.total_score_percent}</span>
                        <button
                          className="text-button"
                          onClick={() => navigate(`/review/${s.id}`)}
                        >
                          Review Session →
                        </button>
                      </div>
                    ))}
                  </div>
                </article>
              )}
            </section>
          )}

          {/* TAB 3: COURSE & SYLLABUS MANAGEMENT */}
          {activeTab === 'courses' && (
            <section className="table-card course-editor" aria-label="Course and syllabus editor">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">COURSE & SYLLABUS</p>
                  <h2>{selectedCourseId ? 'Edit course syllabus' : 'Configure a course'}</h2>
                </div>
                <label className="filter-label">
                  Saved courses
                  <select
                    value={selectedCourseId}
                    onChange={(event) => openCourse(event.target.value)}
                  >
                    <option value="">Create a course</option>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.name} ({course.code})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <form className="question-form" onSubmit={saveCourse}>
                <div className="form-grid">
                  <label>
                    Course name
                    <input
                      required
                      maxLength={255}
                      value={courseForm.name}
                      onChange={(event) =>
                        setCourseForm({ ...courseForm, name: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Subject
                    <input
                      value={courseForm.subject}
                      maxLength={255}
                      onChange={(event) =>
                        setCourseForm({ ...courseForm, subject: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Course code
                    <input
                      required
                      maxLength={50}
                      value={courseForm.code}
                      onChange={(event) =>
                        setCourseForm({ ...courseForm, code: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Academic level
                    <input
                      value={courseForm.academic_level}
                      maxLength={100}
                      placeholder="e.g. Undergraduate"
                      onChange={(event) =>
                        setCourseForm({ ...courseForm, academic_level: event.target.value })
                      }
                    />
                  </label>
                </div>

                <label>
                  Course description
                  <textarea
                    rows={2}
                    value={courseForm.description}
                    onChange={(event) =>
                      setCourseForm({ ...courseForm, description: event.target.value })
                    }
                  />
                </label>

                <label>
                  Complete syllabus
                  <textarea
                    required
                    rows={10}
                    value={courseForm.syllabus_text}
                    onChange={(event) =>
                      setCourseForm({ ...courseForm, syllabus_text: event.target.value })
                    }
                    placeholder="Paste the original course syllabus here. It is stored as the source of truth."
                  />
                </label>

                <div className="section-heading" style={{ marginTop: '16px' }}>
                  <div>
                    <p className="eyebrow">AUTONOMOUS INTERVIEW</p>
                    <h3>Interview defaults</h3>
                  </div>
                </div>

                <div className="form-grid">
                  <label>
                    Question count
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={courseForm.interview_config.max_questions}
                      onChange={(event) =>
                        setInterviewConfig('max_questions', Number(event.target.value))
                      }
                    />
                  </label>
                  <label>
                    Duration (minutes)
                    <input
                      type="number"
                      min="1"
                      max="120"
                      value={Math.round(courseForm.interview_config.max_duration_sec / 60)}
                      onChange={(event) =>
                        setInterviewConfig('max_duration_sec', Number(event.target.value) * 60)
                      }
                    />
                  </label>
                  <label>
                    Difficulty
                    <select
                      value={courseForm.interview_config.difficulty}
                      onChange={(event) =>
                        setInterviewConfig('difficulty', event.target.value)
                      }
                    >
                      <option value="easy">Easy</option>
                      <option value="medium">Medium</option>
                      <option value="hard">Hard</option>
                    </select>
                  </label>
                </div>

                {!!selectedCourse?.topics?.length && (
                  <fieldset className="topic-coverage">
                    <legend>Topics to cover (leave all unchecked to include every topic)</legend>
                    {selectedCourse.topics.map((topic) => (
                      <label key={topic.id}>
                        <input
                          type="checkbox"
                          checked={courseForm.interview_config.topic_ids.includes(topic.id)}
                          onChange={() => toggleInterviewTopic(topic.id)}
                        />
                        {topic.name}
                      </label>
                    ))}
                  </fieldset>
                )}

                <div className="row-actions">
                  <button className="button primary" type="submit" disabled={saving}>
                    {saving ? 'Saving…' : 'Save course and syllabus'}
                  </button>
                  {selectedCourseId && (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={saving || !courseForm.syllabus_text.trim()}
                      onClick={analyzeSyllabus}
                    >
                      Analyze syllabus with Groq
                    </button>
                  )}
                </div>
              </form>

              {selectedCourse?.syllabus_analysis?.modules?.length > 0 && (
                <section className="syllabus-review">
                  <p className="eyebrow">EXTRACTED TOPICS · REVIEW & EDIT</p>
                  {selectedCourse.syllabus_analysis.modules.map((module, index) => (
                    <details key={`${module.name}-${index}`} open>
                      <summary>{module.name}</summary>
                      <div className="topic-editor-list">
                        {(module.topics || []).map((item) => {
                          const topic = selectedCourse.topics.find(
                            (savedTopic) =>
                              savedTopic.name.toLowerCase() === item.name.toLowerCase(),
                          )
                          if (!topic) return <p key={item.name}>{item.name}</p>
                          return (
                            <div className="topic-editor-row" key={topic.id}>
                              <input
                                aria-label={`Topic name for ${item.name}`}
                                value={topicDrafts[topic.id] ?? topic.name}
                                onChange={(event) =>
                                  setTopicDrafts({
                                    ...topicDrafts,
                                    [topic.id]: event.target.value,
                                  })
                                }
                              />
                              <button
                                className="button secondary"
                                type="button"
                                onClick={() => saveTopicName(topic)}
                              >
                                Save topic
                              </button>
                              <span className="muted">{item.key_concepts?.join(' · ')}</span>
                            </div>
                          )
                        })}
                      </div>
                    </details>
                  ))}
                </section>
              )}

              {selectedCourseId && selectedCourse && (
                <div style={{ marginTop: '28px', borderTop: '1px solid #e9e7e2', paddingTop: '20px' }}>
                  <DocumentManager
                    course={selectedCourse}
                    onDocumentsChanged={() => loadData(selectedCourseFilter, { silent: true })}
                  />
                </div>
              )}
            </section>
          )}

          {/* TAB 4: ALL SESSIONS REVIEW */}
          {activeTab === 'sessions' && (
            <section className="table-card recent-section" aria-label="Student session review">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">SESSION DIRECTORY</p>
                  <h2>All Student Sessions</h2>
                </div>
                <label className="filter-label">
                  Course
                  <select
                    aria-label="Filter sessions by course"
                    value={selectedCourseFilter}
                    onChange={(event) => setSelectedCourseFilter(event.target.value)}
                  >
                    <option value="">All courses</option>
                    {courses.map((course) => (
                      <option value={course.id} key={course.id}>
                        {course.name} ({course.code})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {sessions.length ? (
                <div className="session-list">
                  {sessions.map((session) => (
                    <div className="session-row" key={session.id}>
                      <div>
                        <strong>{session.student_name || 'Student'}</strong>
                        <span>
                          {session.student_email && `${session.student_email} · `}
                          {session.course_name} · {formatSessionDate(session.created_at)}
                        </span>
                      </div>
                      <span className={`status-tag ${session.status}`}>
                        {session.status.replace('_', ' ')}
                      </span>
                      <span className="session-score">
                        {formatRatioPercent(session.total_score)}
                      </span>
                      <button
                        className="text-button"
                        onClick={() => navigate(`/review/${session.id}`)}
                      >
                        Review →
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <h3>No sessions to review</h3>
                  <p>Completed student viva sessions will appear here.</p>
                </div>
              )}
            </section>
          )}

          {/* TAB 5: CUSTOM VIVA BUILDER */}
          {activeTab === 'builder' && (
            <CustomVivaBuilder navigate={navigate} courses={courses} />
          )}

          {/* TAB 6: QUESTION BANK */}
          {activeTab === 'questions' && (
            <QuestionBank navigate={navigate} initialCourseId={selectedCourseFilter} />
          )}

          {/* TAB 7: ASSIGNMENTS & DEADLINES */}
          {activeTab === 'assignments' && (
            <AssignmentManager courses={courses} onNavigate={navigate} />
          )}

          {/* TAB 8: DETAILED REPORTS & EXPORT */}
          {activeTab === 'reports' && (
            <TeacherReportsManager courses={courses} onNavigate={navigate} />
          )}

          {/* Question Bank quick link */}
          <section className="teacher-tools" style={{ marginTop: '36px' }}>
            <article>
              <span className="eyebrow">QUESTION BANK</span>
              <h3>Course Question Repository</h3>
              <p>Review, create, and manage curated oral exam questions across your course topics.</p>
              <button className="text-button" onClick={() => navigate('/questions')}>
                Open question bank →
              </button>
            </article>
            <article>
              <span className="eyebrow">TEACHING STUDIO</span>
              <h3>{courses.length} Active Courses</h3>
              <p>Syllabi, interview configurations, and rubric criteria are persisted with each course.</p>
            </article>
          </section>
        </>
      )}
    </main>
  )
}
