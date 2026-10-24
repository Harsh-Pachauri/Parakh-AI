import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import {
  formatReportScore,
  getPerformanceTier,
  serializeReportParams,
  validateDateRange,
} from '../utils/reportHelpers'
import { formatAssignmentDate } from '../utils/assignmentHelpers'
import StudentPerformanceReportModal from './StudentPerformanceReportModal'

export default function TeacherReportsManager({ courses = [], onNavigate }) {
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters
  const [courseFilter, setCourseFilter] = useState('all')
  const [topicFilter, setTopicFilter] = useState('all')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [dateError, setDateError] = useState('')

  // Student Drilldown Modal state
  const [selectedStudentId, setSelectedStudentId] = useState(null)

  // Download states
  const [pdfDownloading, setPdfDownloading] = useState(false)
  const [csvDownloading, setCsvDownloading] = useState(false)

  // Selected course object and its topics
  const selectedCourse = useMemo(
    () => courses.find((c) => c.id === courseFilter),
    [courses, courseFilter]
  )
  const availableTopics = selectedCourse?.topics || []

  const loadClassReport = async () => {
    const dateVal = validateDateRange(fromDate, toDate)
    if (!dateVal.valid) {
      setDateError(dateVal.error || 'Invalid date range.')
      return
    }
    setDateError('')
    setLoading(true)
    setError('')

    try {
      const params = {}
      if (courseFilter !== 'all') params.course_id = courseFilter
      if (topicFilter !== 'all') params.topic_id = topicFilter
      if (fromDate) params.from_date = new Date(fromDate).toISOString()
      if (toDate) params.to_date = new Date(toDate).toISOString()

      const res = await apiClient.get('/api/reports/teacher/class', { params })
      setReportData(res.data)
    } catch (err) {
      setError(err.userMessage || 'Could not load class performance reports.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadClassReport()
  }, [courseFilter, topicFilter])

  const handleDownloadClassPdf = async () => {
    setPdfDownloading(true)
    try {
      const params = {}
      if (courseFilter !== 'all') params.course_id = courseFilter
      if (topicFilter !== 'all') params.topic_id = topicFilter
      if (fromDate) params.from_date = new Date(fromDate).toISOString()
      if (toDate) params.to_date = new Date(toDate).toISOString()

      const res = await apiClient.get('/api/reports/teacher/class/pdf', {
        params,
        responseType: 'blob',
      })
      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = blobUrl
      link.setAttribute('download', `parakh-class-report-${courseFilter}.pdf`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(blobUrl)
    } catch {
      setError('Could not download class PDF report.')
    } finally {
      setPdfDownloading(false)
    }
  }

  const handleExportCsv = async () => {
    setCsvDownloading(true)
    try {
      const params = {}
      if (courseFilter !== 'all') params.course_id = courseFilter
      if (topicFilter !== 'all') params.topic_id = topicFilter
      if (fromDate) params.from_date = new Date(fromDate).toISOString()
      if (toDate) params.to_date = new Date(toDate).toISOString()

      const res = await apiClient.get('/api/reports/export', {
        params,
        responseType: 'blob',
      })
      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const link = document.createElement('a')
      link.href = blobUrl
      link.setAttribute('download', `parakh-oral-reports-${courseFilter}.csv`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(blobUrl)
    } catch {
      setError('Could not export CSV report.')
    } finally {
      setCsvDownloading(false)
    }
  }

  return (
    <div className="teacher-reports-container">
      {/* Header & Export Toolbar */}
      <div className="section-header-row">
        <div>
          <h2>Performance Reports &amp; Analytics Export</h2>
          <p className="section-subtitle">
            Class-wide oral proficiency summaries, individual student diagnostic drilldowns, and audit-ready exports.
          </p>
        </div>
        <div className="action-buttons-inline">
          <button
            className="btn-outline"
            onClick={handleExportCsv}
            disabled={csvDownloading || loading}
          >
            {csvDownloading ? 'Exporting...' : '📥 Export CSV'}
          </button>
          <button
            className="btn-primary"
            onClick={handleDownloadClassPdf}
            disabled={pdfDownloading || loading}
          >
            {pdfDownloading ? 'Generating...' : '📄 Download Class PDF'}
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
          <button className="btn-link close-alert" onClick={() => setError('')}>✕</button>
        </div>
      )}

      {dateError && (
        <div className="alert alert-danger" role="alert">
          {dateError}
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="toolbar-row" style={{ flexWrap: 'wrap' }}>
        <div className="filter-group">
          <label>Course:</label>
          <select
            value={courseFilter}
            onChange={(e) => {
              setCourseFilter(e.target.value)
              setTopicFilter('all')
            }}
          >
            <option value="all">All Enrolled Courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.code})
              </option>
            ))}
          </select>
        </div>

        {availableTopics.length > 0 && (
          <div className="filter-group">
            <label>Topic:</label>
            <select
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
            >
              <option value="all">All Course Topics</option>
              {availableTopics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="filter-group">
          <label>From:</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>To:</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </div>

        <button className="btn-sm btn-secondary" onClick={loadClassReport}>
          Apply Dates
        </button>
      </div>

      {loading ? (
        <div className="loading-state">
          <p>Compiling class performance analytics and student score histories...</p>
        </div>
      ) : !reportData ? (
        <div className="empty-state">
          <p>No performance data available for the selected parameters.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Summary KPI Cards */}
          <div className="stats-kpi-grid">
            <div className="kpi-card">
              <span className="kpi-label">Active Students</span>
              <span className="kpi-value">{reportData.summary.total_students}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Completed Vivas</span>
              <span className="kpi-value text-success">{reportData.summary.completed_sessions}</span>
              <small className="cell-subtext">Out of {reportData.summary.total_sessions} total</small>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Class Average Score</span>
              <span className="kpi-value text-primary">{reportData.summary.average_score_percent}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Evaluated Topics</span>
              <span className="kpi-value">{reportData.topics.length}</span>
            </div>
          </div>

          {/* Class Score Distribution Bar */}
          {reportData.score_distribution && (
            <div className="report-card-section">
              <h4 style={{ margin: '0 0 10px', fontSize: '15px' }}>Class Score Distribution</h4>
              <div className="dist-bar">
                <span
                  className="dist-seg-mastery"
                  style={{ width: reportData.score_distribution.mastery_pct }}
                  title={`Mastery: ${reportData.score_distribution.mastery}`}
                />
                <span
                  className="dist-seg-proficient"
                  style={{ width: reportData.score_distribution.proficient_pct }}
                  title={`Proficient: ${reportData.score_distribution.proficient}`}
                />
                <span
                  className="dist-seg-developing"
                  style={{ width: reportData.score_distribution.developing_pct }}
                  title={`Developing: ${reportData.score_distribution.developing}`}
                />
                <span
                  className="dist-seg-attention"
                  style={{ width: reportData.score_distribution.attention_pct }}
                  title={`Needs Attention: ${reportData.score_distribution.attention}`}
                />
              </div>
              <div className="dist-legend">
                <span className="dist-legend-item">
                  <i className="dist-legend-dot dist-seg-mastery" /> Mastery (80%+):{' '}
                  <strong>{reportData.score_distribution.mastery}</strong> ({reportData.score_distribution.mastery_pct})
                </span>
                <span className="dist-legend-item">
                  <i className="dist-legend-dot dist-seg-proficient" /> Proficient (65-79%):{' '}
                  <strong>{reportData.score_distribution.proficient}</strong> ({reportData.score_distribution.proficient_pct})
                </span>
                <span className="dist-legend-item">
                  <i className="dist-legend-dot dist-seg-developing" /> Developing (50-64%):{' '}
                  <strong>{reportData.score_distribution.developing}</strong> ({reportData.score_distribution.developing_pct})
                </span>
                <span className="dist-legend-item">
                  <i className="dist-legend-dot dist-seg-attention" /> Needs Attention (&lt;50%):{' '}
                  <strong>{reportData.score_distribution.attention}</strong> ({reportData.score_distribution.attention_pct})
                </span>
              </div>
            </div>
          )}

          {/* Adaptive Practice vs. Assigned Assessments Breakdown */}
          {reportData.activity_breakdown && (
            <div className="report-card-section">
              <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>
                🎯 Assessment vs. Adaptive Practice Activity
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '6px' }}>📋 Assigned Assessments</div>
                  <div style={{ fontSize: '13px', color: '#77808a' }}>
                    Completed: <b style={{ color: '#faf8f5' }}>{reportData.activity_breakdown.assigned_assessments.count}</b> · Average: <b style={{ color: '#bc603e' }}>{reportData.activity_breakdown.assigned_assessments.average_score_percent}</b>
                  </div>
                </div>
                <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '6px' }}>🎯 Adaptive Viva Practice</div>
                  <div style={{ fontSize: '13px', color: '#77808a' }}>
                    Completed: <b style={{ color: '#faf8f5' }}>{reportData.activity_breakdown.adaptive_practice.count}</b> · Average: <b style={{ color: '#41765f' }}>{reportData.activity_breakdown.adaptive_practice.average_score_percent}</b>
                  </div>
                  {reportData.activity_breakdown.adaptive_practice.difficulty_breakdown && (
                    <div style={{ fontSize: '12px', color: '#77808a', marginTop: '6px' }}>
                      Questions: {reportData.activity_breakdown.adaptive_practice.difficulty_breakdown.easy} Easy · {reportData.activity_breakdown.adaptive_practice.difficulty_breakdown.medium} Medium · {reportData.activity_breakdown.adaptive_practice.difficulty_breakdown.hard} Hard
                      {reportData.activity_breakdown.adaptive_practice.stepped_up_to_hard_count > 0 && (
                        <span> ({reportData.activity_breakdown.adaptive_practice.stepped_up_to_hard_count} escalated to Hard)</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Class-wide Weak Topics Notice */}
          {reportData.class_weaknesses && reportData.class_weaknesses.length > 0 && (
            <div className="coaching-notice-box">
              <strong style={{ color: 'var(--red)' }}>⚠️ Identified Class-Wide Weakness Topics:</strong>
              <ul style={{ margin: '8px 0 0', paddingLeft: '20px' }}>
                {reportData.class_weaknesses.map((w) => (
                  <li key={w.topic_id} style={{ marginBottom: '4px' }}>
                    <strong>{w.topic_name}</strong> ({w.average_score_percent} class average across {w.evaluated_count} questions) — {w.recommendation}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Student Performance Roster Table */}
          <div className="report-card-section">
            <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Student Performance Roster</h4>
            {reportData.students.length === 0 ? (
              <p className="cell-subtext">No student records found matching the active filters.</p>
            ) : (
              <div className="table-responsive">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Email</th>
                      <th>Viva Attempts</th>
                      <th>Completed</th>
                      <th>Average Score</th>
                      <th>Last Active</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.students.map((s) => (
                      <tr key={s.student_id}>
                        <td><strong>{s.student_name}</strong></td>
                        <td>{s.student_email}</td>
                        <td>{s.total_sessions}</td>
                        <td>{s.completed_sessions}</td>
                        <td>
                          {s.average_score_percent !== '—' ? (
                            <strong>{s.average_score_percent}</strong>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td>{formatAssignmentDate(s.last_active_at)}</td>
                        <td>
                          <button
                            className="btn-sm btn-secondary"
                            onClick={() => setSelectedStudentId(s.student_id)}
                          >
                            Detailed Report →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Topic Performance Breakdown Table */}
          <div className="report-card-section">
            <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Topic-Wise Evaluation Breakdown</h4>
            {reportData.topics.length === 0 ? (
              <p className="cell-subtext">No topic answers recorded in this period.</p>
            ) : (
              <div className="table-responsive">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Course</th>
                      <th>Total Attempts</th>
                      <th>Evaluated Answers</th>
                      <th>Class Average</th>
                      <th>Classification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.topics.map((t) => (
                      <tr key={t.topic_id}>
                        <td><strong>{t.topic_name}</strong></td>
                        <td>{t.course_name}</td>
                        <td>{t.attempt_count}</td>
                        <td>{t.evaluated_count}</td>
                        <td><strong>{t.average_score_percent}</strong></td>
                        <td>
                          <span className={`status-tag ${t.status}`}>
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Student Drilldown Modal */}
      {selectedStudentId && (
        <StudentPerformanceReportModal
          studentId={selectedStudentId}
          courseId={courseFilter !== 'all' ? courseFilter : null}
          onClose={() => setSelectedStudentId(null)}
          onNavigate={onNavigate}
        />
      )}
    </div>
  )
}
