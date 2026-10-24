import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import { formatReportScore, getPerformanceTier } from '../utils/reportHelpers'
import { formatRatioPercent } from '../utils/formatters'
import { formatAssignmentDate } from '../utils/assignmentHelpers'

export default function StudentPerformanceReportModal({
  studentId = null, // null means current student ('/api/reports/student/me')
  courseId = null,
  onClose,
  onNavigate,
}) {
  const [reportData, setReportData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pdfDownloading, setPdfDownloading] = useState(false)

  const isTeacherView = Boolean(studentId)

  useEffect(() => {
    let isMounted = true

    async function fetchReport() {
      setLoading(true)
      setError('')
      try {
        const endpoint = isTeacherView
          ? `/api/reports/teacher/student/${studentId}`
          : '/api/reports/student/me'

        const params = {}
        if (courseId) params.course_id = courseId

        const res = await apiClient.get(endpoint, { params })
        if (isMounted) {
          setReportData(res.data)
        }
      } catch (err) {
        if (isMounted) {
          setError(err.userMessage || 'Could not load the detailed performance report.')
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    fetchReport()
    return () => {
      isMounted = false
    }
  }, [studentId, courseId, isTeacherView])

  const handleDownloadPdf = async () => {
    setPdfDownloading(true)
    try {
      const endpoint = isTeacherView
        ? `/api/reports/teacher/student/${studentId}/pdf`
        : '/api/reports/student/me/pdf'

      const params = {}
      if (courseId) params.course_id = courseId

      const res = await apiClient.get(endpoint, {
        params,
        responseType: 'blob',
      })

      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = blobUrl
      const filename = isTeacherView
        ? `student-report-${studentId}.pdf`
        : 'parakh-student-performance-report.pdf'
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(blobUrl)
    } catch {
      setError('Could not generate the PDF report. Please try again.')
    } finally {
      setPdfDownloading(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-content modal-xl">
        <div className="modal-header">
          <div>
            <h3>Oral Performance Report</h3>
            {reportData && (
              <p className="modal-subtitle">
                {reportData.student.full_name} ({reportData.student.email}) •{' '}
                {reportData.course_scope?.course_name || 'All Courses'}
              </p>
            )}
          </div>
          <div className="modal-actions-inline">
            <button
              className="btn-primary"
              onClick={handleDownloadPdf}
              disabled={pdfDownloading || loading || !reportData}
            >
              {pdfDownloading ? 'Generating PDF...' : '📄 Download PDF'}
            </button>
            <button className="btn-close" onClick={onClose} title="Close">✕</button>
          </div>
        </div>

        <div className="modal-body">
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="loading-state">
              <p>Analyzing oral examination records and computing diagnostics...</p>
            </div>
          ) : !reportData ? (
            <div className="empty-state">
              <p>No report records found for this student.</p>
            </div>
          ) : (
            <div>
              {/* Executive Summary Cards */}
              <div className="stats-kpi-grid" style={{ marginBottom: '20px' }}>
                <div className="kpi-card">
                  <span className="kpi-label">Completed Vivas</span>
                  <span className="kpi-value text-success">
                    {reportData.overall.completed_sessions}
                  </span>
                  <small className="cell-subtext">
                    Out of {reportData.overall.total_sessions} attempted
                  </small>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Average Score</span>
                  <span className="kpi-value text-primary">
                    {reportData.overall.average_score_percent}
                  </span>
                  <small className="cell-subtext">
                    {getPerformanceTier(reportData.overall.average_score).label}
                  </small>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Evaluated Answers</span>
                  <span className="kpi-value">
                    {reportData.overall.total_evaluated_answers}
                  </span>
                  <small className="cell-subtext">Questions answered</small>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Primary Strength</span>
                  <span className="kpi-value text-success" style={{ fontSize: '16px', marginTop: '6px' }}>
                    {reportData.strengths.length > 0
                      ? reportData.strengths[0].topic_name
                      : 'Developing'}
                  </span>
                </div>
              </div>

              {/* Competency Dimensions */}
              {reportData.overall.dimension_averages && (
                <div className="report-card-section" style={{ marginBottom: '24px' }}>
                  <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Oral Competency Breakdown</h4>
                  <div className="dimension-grid">
                    <div className="dimension-card">
                      <div className="dimension-header">
                        <span>Factual Correctness</span>
                        <strong>{formatRatioPercent(reportData.overall.dimension_averages.correctness)}</strong>
                      </div>
                      <div className="score-track">
                        <i style={{ width: `${Math.round((reportData.overall.dimension_averages.correctness || 0) * 100)}%` }} />
                      </div>
                    </div>
                    <div className="dimension-card">
                      <div className="dimension-header">
                        <span>Answer Completeness</span>
                        <strong>{formatRatioPercent(reportData.overall.dimension_averages.completeness)}</strong>
                      </div>
                      <div className="score-track">
                        <i style={{ width: `${Math.round((reportData.overall.dimension_averages.completeness || 0) * 100)}%` }} />
                      </div>
                    </div>
                    <div className="dimension-card">
                      <div className="dimension-header">
                        <span>Spoken Clarity</span>
                        <strong>{formatRatioPercent(reportData.overall.dimension_averages.clarity)}</strong>
                      </div>
                      <div className="score-track">
                        <i style={{ width: `${Math.round((reportData.overall.dimension_averages.clarity || 0) * 100)}%` }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Diagnostic Guidance */}
              {reportData.coaching_summary && (
                <div className="coaching-notice-box" style={{ marginBottom: '24px' }}>
                  <strong>Diagnostic Recommendation:</strong> {reportData.coaching_summary}
                </div>
              )}

              {/* Score History Over Time */}
              {reportData.score_history && reportData.score_history.length > 0 && (
                <div className="report-card-section" style={{ marginBottom: '24px' }}>
                  <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Score History &amp; Progress</h4>
                  <div className="score-history-chips">
                    {reportData.score_history.map((h, idx) => (
                      <div key={h.session_id} className="history-chip">
                        <span className="history-num">#{idx + 1}</span>
                        <strong className="history-pct">{h.score_percent}</strong>
                        <span className="history-date">{h.date ? h.date.substring(0, 10) : ''}</span>
                        <span className="history-course">{h.course_code || h.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Topic-Wise Breakdown */}
              <div className="report-card-section" style={{ marginBottom: '24px' }}>
                <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Topic-Wise Performance Breakdown</h4>
                {reportData.topic_breakdown.length === 0 ? (
                  <p className="cell-subtext">No evaluated topics recorded yet.</p>
                ) : (
                  <div className="table-responsive">
                    <table className="custom-table">
                      <thead>
                        <tr>
                          <th>Topic</th>
                          <th>Course</th>
                          <th>Questions Evaluated</th>
                          <th>Average Score</th>
                          <th>Status</th>
                          <th>Primary Gap / Focus</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.topic_breakdown.map((t) => (
                          <tr key={t.topic_id}>
                            <td><strong>{t.topic_name}</strong></td>
                            <td>{t.course_code || t.course_name}</td>
                            <td>{t.evaluated_count}</td>
                            <td><strong>{t.average_score_percent}</strong></td>
                            <td>
                              <span className={`status-tag ${t.status}`}>
                                {t.status}
                              </span>
                            </td>
                            <td style={{ fontSize: '12px', color: '#77808a' }}>
                              {t.primary_gap}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Recent Examination Attempts */}
              <div className="report-card-section">
                <h4 style={{ margin: '0 0 12px', fontSize: '15px' }}>Recent Viva Attempts &amp; Sessions</h4>
                {reportData.recent_attempts.length === 0 ? (
                  <p className="cell-subtext">No examination attempts on record.</p>
                ) : (
                  <div className="table-responsive">
                    <table className="custom-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Examination</th>
                          <th>Type</th>
                          <th>Course</th>
                          <th>Status</th>
                          <th>Score</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.recent_attempts.map((att) => (
                          <tr key={att.session_id}>
                            <td>{formatAssignmentDate(att.created_at)}</td>
                            <td><strong>{att.title}</strong></td>
                            <td>
                              <span className="badge badge-subtle">{att.type}</span>
                            </td>
                            <td>{att.course_code || att.course_name}</td>
                            <td>
                              <span className={`status-tag ${att.status}`}>
                                {att.status}
                              </span>
                            </td>
                            <td>
                              {att.score_percent !== '—' ? (
                                <strong>{att.score_percent}</strong>
                              ) : (
                                <span className="text-muted">—</span>
                              )}
                            </td>
                            <td>
                              {onNavigate && (
                                <button
                                  className="btn-sm btn-secondary"
                                  onClick={() => {
                                    onClose()
                                    onNavigate(isTeacherView ? `session-review/${att.session_id}` : `report/${att.session_id}`)
                                  }}
                                >
                                  {isTeacherView ? 'Review' : 'View Report'}
                                </button>
                              )}
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
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
