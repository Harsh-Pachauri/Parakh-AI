import { useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'
import {
  filterAssignments,
  formatAssignmentDate,
  formatAssignmentStatus,
  getAssignmentSummaryStats,
  validateAssignmentForm,
} from '../utils/assignmentHelpers'
import { formatRatioPercent } from '../utils/formatters'

const initialForm = {
  title: '',
  course_id: '',
  assessment_id: '',
  instructions: '',
  start_date: '',
  deadline: '',
  attempt_limit: 1,
  is_active: true,
}

export default function AssignmentManager({ courses = [], onNavigate }) {
  const [assignments, setAssignments] = useState([])
  const [publishedAssessments, setPublishedAssessments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // Filter & Search states
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [courseFilter, setCourseFilter] = useState('all')

  // Form modal states
  const [showFormModal, setShowFormModal] = useState(false)
  const [editingAssignmentId, setEditingAssignmentId] = useState(null)
  const [formData, setFormData] = useState(initialForm)
  const [formErrors, setFormErrors] = useState({})
  const [formSubmitting, setFormSubmitting] = useState(false)

  // Submissions modal states
  const [submissionsModalAssignment, setSubmissionsModalAssignment] = useState(null)
  const [submissionsData, setSubmissionsData] = useState(null)
  const [submissionsLoading, setSubmissionsLoading] = useState(false)

  const loadAssignments = async () => {
    setLoading(true)
    setError('')
    try {
      const [assignRes, assessRes] = await Promise.all([
        apiClient.get('/api/assignments'),
        apiClient.get('/api/assessments', { params: { is_published: true } }),
      ])
      setAssignments(Array.isArray(assignRes.data) ? assignRes.data : [])
      setPublishedAssessments(Array.isArray(assessRes.data) ? assessRes.data : [])
    } catch (err) {
      setError(err.userMessage || 'Failed to load assignments and assessments.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAssignments()
  }, [])

  // Filter assessments based on selected course in form
  const availableAssessmentsForCourse = useMemo(() => {
    if (!formData.course_id) return []
    return publishedAssessments.filter((a) => a.course_id === formData.course_id)
  }, [publishedAssessments, formData.course_id])

  // Filtered assignments
  const filteredAssignments = useMemo(() => {
    let list = assignments
    if (courseFilter !== 'all') {
      list = list.filter((a) => a.course_id === courseFilter)
    }
    return filterAssignments(list, searchQuery, statusFilter)
  }, [assignments, courseFilter, searchQuery, statusFilter])

  // Summary statistics
  const stats = useMemo(() => {
    return getAssignmentSummaryStats(assignments)
  }, [assignments])

  const openCreateModal = () => {
    setEditingAssignmentId(null)
    setFormData({
      ...initialForm,
      course_id: courses[0]?.id || '',
    })
    setFormErrors({})
    setShowFormModal(true)
  }

  const openEditModal = (assignment) => {
    setEditingAssignmentId(assignment.id)
    setFormData({
      title: assignment.title || '',
      course_id: assignment.course_id || '',
      assessment_id: assignment.assessment_id || '',
      instructions: assignment.instructions || '',
      start_date: assignment.start_date ? assignment.start_date.substring(0, 16) : '',
      deadline: assignment.deadline ? assignment.deadline.substring(0, 16) : '',
      attempt_limit: assignment.attempt_limit || 1,
      is_active: assignment.is_active ?? true,
    })
    setFormErrors({})
    setShowFormModal(true)
  }

  const handleFormSubmit = async (e) => {
    e.preventDefault()
    const { valid, errors } = validateAssignmentForm(formData)
    if (!valid) {
      setFormErrors(errors)
      return
    }

    setFormSubmitting(true)
    setError('')
    try {
      const payload = {
        title: formData.title.trim(),
        course_id: formData.course_id,
        assessment_id: formData.assessment_id,
        instructions: formData.instructions ? formData.instructions.trim() : null,
        start_date: formData.start_date ? new Date(formData.start_date).toISOString() : null,
        deadline: formData.deadline ? new Date(formData.deadline).toISOString() : null,
        attempt_limit: Number(formData.attempt_limit),
        is_active: Boolean(formData.is_active),
      }

      if (editingAssignmentId) {
        await apiClient.put(`/api/assignments/${editingAssignmentId}`, payload)
        setNotice('Assignment updated successfully.')
      } else {
        await apiClient.post('/api/assignments', payload)
        setNotice('Assessment scheduled and assigned successfully.')
      }

      setShowFormModal(false)
      loadAssignments()
    } catch (err) {
      setError(err.userMessage || 'Could not save assignment. Please check inputs.')
    } finally {
      setFormSubmitting(false)
    }
  }

  const handleDeleteOrCancel = async (assignment) => {
    const hasSubmissions = (assignment.total_submissions || 0) > 0
    const promptMsg = hasSubmissions
      ? `This assignment has ${assignment.total_submissions} student submission(s). Cancelling it will close the assignment while preserving student scores. Proceed?`
      : `Are you sure you want to delete assignment "${assignment.title}"?`

    if (!window.confirm(promptMsg)) return

    try {
      const res = await apiClient.delete(`/api/assignments/${assignment.id}`)
      setNotice(res.data?.detail || 'Assignment updated.')
      loadAssignments()
    } catch (err) {
      setError(err.userMessage || 'Could not delete or cancel assignment.')
    }
  }

  const openSubmissionsModal = async (assignment) => {
    setSubmissionsModalAssignment(assignment)
    setSubmissionsLoading(true)
    setSubmissionsData(null)
    try {
      const res = await apiClient.get(`/api/assignments/${assignment.id}/submissions`)
      setSubmissionsData(res.data)
    } catch (err) {
      setError(err.userMessage || 'Could not load assignment submissions.')
    } finally {
      setSubmissionsLoading(false)
    }
  }

  return (
    <div className="assignment-manager-container">
      {/* Header bar */}
      <div className="section-header-row">
        <div>
          <h2>Assessment Assignments & Deadlines</h2>
          <p className="section-subtitle">
            Schedule custom oral assessments for your classes, set attempt limits, and track student submissions.
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={openCreateModal}
          disabled={publishedAssessments.length === 0}
          title={publishedAssessments.length === 0 ? 'Create and publish an assessment first' : ''}
        >
          + Assign Assessment
        </button>
      </div>

      {notice && (
        <div className="alert alert-success" role="alert">
          {notice}
          <button className="btn-link close-alert" onClick={() => setNotice('')}>✕</button>
        </div>
      )}

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
          <button className="btn-link close-alert" onClick={() => setError('')}>✕</button>
        </div>
      )}

      {publishedAssessments.length === 0 && !loading && (
        <div className="empty-notice-card">
          <h4>No Published Assessments Available</h4>
          <p>
            You must build and publish a custom assessment before assigning it with deadlines.
          </p>
        </div>
      )}

      {/* Summary KPI row */}
      <div className="stats-kpi-grid">
        <div className="kpi-card">
          <span className="kpi-label">Total Assignments</span>
          <span className="kpi-value">{stats.total}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Active / Open</span>
          <span className="kpi-value text-success">{stats.active}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Scheduled (Upcoming)</span>
          <span className="kpi-value text-info">{stats.scheduled}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Closed / Overdue</span>
          <span className="kpi-value text-muted">{stats.closed}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Total Student Submissions</span>
          <span className="kpi-value text-primary">{stats.totalSubmissions}</span>
        </div>
      </div>

      {/* Filter and search toolbar */}
      <div className="toolbar-row">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search by title, course, or assessment..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="filter-group">
          <label>Course:</label>
          <select value={courseFilter} onChange={(e) => setCourseFilter(e.target.value)}>
            <option value="all">All Courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.code})
              </option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label>Status:</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="scheduled">Scheduled</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      {/* Assignments Table */}
      {loading ? (
        <div className="loading-state">
          <p>Loading assignments and submissions...</p>
        </div>
      ) : filteredAssignments.length === 0 ? (
        <div className="empty-state">
          <p>No assignments match the selected criteria.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="custom-table">
            <thead>
              <tr>
                <th>Assignment Title</th>
                <th>Course</th>
                <th>Assessment</th>
                <th>Scheduled Window</th>
                <th>Attempt Limit</th>
                <th>Status</th>
                <th>Submissions</th>
                <th>Average Score</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAssignments.map((assignment) => {
                const statusMeta = formatAssignmentStatus(assignment.status)
                return (
                  <tr key={assignment.id}>
                    <td>
                      <strong>{assignment.title}</strong>
                      {assignment.instructions && (
                        <p className="cell-subtext">{assignment.instructions}</p>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-subtle">
                        {assignment.course_code || assignment.course_name || 'Course'}
                      </span>
                    </td>
                    <td>
                      <span>{assignment.assessment_title || 'Custom Viva'}</span>
                      {assignment.duration_minutes && (
                        <span className="cell-subtext"> • {assignment.duration_minutes}m</span>
                      )}
                    </td>
                    <td>
                      <div className="date-window">
                        <span>From: {formatAssignmentDate(assignment.start_date, 'Immediate')}</span>
                        <span>Due: {formatAssignmentDate(assignment.deadline, 'No deadline')}</span>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-secondary">
                        {assignment.attempt_limit} max
                      </span>
                    </td>
                    <td>
                      <span className={statusMeta.className}>{statusMeta.label}</span>
                    </td>
                    <td>
                      <button
                        className="btn-link"
                        onClick={() => openSubmissionsModal(assignment)}
                        title="View student attempts"
                      >
                        <strong>{assignment.completed_count || 0}</strong> completed
                        <span className="cell-subtext"> ({assignment.total_submissions || 0} attempts)</span>
                      </button>
                    </td>
                    <td>
                      {assignment.average_score !== null && assignment.average_score !== undefined ? (
                        <strong>{formatRatioPercent(assignment.average_score)}</strong>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <div className="action-buttons-inline">
                        <button
                          className="btn-sm btn-secondary"
                          onClick={() => openSubmissionsModal(assignment)}
                        >
                          Submissions
                        </button>
                        <button
                          className="btn-sm btn-outline"
                          onClick={() => openEditModal(assignment)}
                        >
                          Edit
                        </button>
                        <button
                          className="btn-sm btn-danger-outline"
                          onClick={() => handleDeleteOrCancel(assignment)}
                          title={(assignment.total_submissions || 0) > 0 ? 'Cancel assignment' : 'Delete assignment'}
                        >
                          {(assignment.total_submissions || 0) > 0 ? 'Cancel' : 'Delete'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Assignment Create / Edit Modal */}
      {showFormModal && (
        <div className="modal-backdrop">
          <div className="modal-content modal-lg">
            <div className="modal-header">
              <h3>{editingAssignmentId ? 'Edit Assignment' : 'Assign & Schedule Oral Assessment'}</h3>
              <button className="btn-close" onClick={() => setShowFormModal(false)}>✕</button>
            </div>
            <form onSubmit={handleFormSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label htmlFor="assign-title">Assignment Title *</label>
                  <input
                    id="assign-title"
                    type="text"
                    required
                    placeholder="e.g., Midterm Oral Exam - Cohort A"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  />
                  {formErrors.title && <span className="error-text">{formErrors.title}</span>}
                </div>

                <div className="form-row">
                  <div className="form-group flex-1">
                    <label htmlFor="assign-course">Course *</label>
                    <select
                      id="assign-course"
                      required
                      disabled={Boolean(editingAssignmentId)}
                      value={formData.course_id}
                      onChange={(e) => {
                        const newCourseId = e.target.value
                        setFormData({
                          ...formData,
                          course_id: newCourseId,
                          assessment_id: '',
                        })
                      }}
                    >
                      <option value="">Select a course</option>
                      {courses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.code})
                        </option>
                      ))}
                    </select>
                    {formErrors.course_id && (
                      <span className="error-text">{formErrors.course_id}</span>
                    )}
                  </div>

                  <div className="form-group flex-1">
                    <label htmlFor="assign-assessment">Published Assessment *</label>
                    <select
                      id="assign-assessment"
                      required
                      disabled={Boolean(editingAssignmentId) || !formData.course_id}
                      value={formData.assessment_id}
                      onChange={(e) => setFormData({ ...formData, assessment_id: e.target.value })}
                    >
                      <option value="">
                        {!formData.course_id
                          ? 'Select course first'
                          : availableAssessmentsForCourse.length === 0
                          ? 'No published assessments in this course'
                          : 'Select custom assessment'}
                      </option>
                      {availableAssessmentsForCourse.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.title} ({a.duration_minutes}m, {a.difficulty})
                        </option>
                      ))}
                    </select>
                    {formErrors.assessment_id && (
                      <span className="error-text">{formErrors.assessment_id}</span>
                    )}
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group flex-1">
                    <label htmlFor="assign-start">Start Date & Time (Optional)</label>
                    <input
                      id="assign-start"
                      type="datetime-local"
                      value={formData.start_date}
                      onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                    />
                    <small className="help-text">Leave blank to open immediately.</small>
                    {formErrors.start_date && (
                      <span className="error-text">{formErrors.start_date}</span>
                    )}
                  </div>

                  <div className="form-group flex-1">
                    <label htmlFor="assign-deadline">Deadline Date & Time (Optional)</label>
                    <input
                      id="assign-deadline"
                      type="datetime-local"
                      value={formData.deadline}
                      onChange={(e) => setFormData({ ...formData, deadline: e.target.value })}
                    />
                    <small className="help-text">Leave blank for no strict deadline.</small>
                    {formErrors.deadline && (
                      <span className="error-text">{formErrors.deadline}</span>
                    )}
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group flex-1">
                    <label htmlFor="assign-attempts">Attempt Limit *</label>
                    <input
                      id="assign-attempts"
                      type="number"
                      min="1"
                      max="100"
                      required
                      value={formData.attempt_limit}
                      onChange={(e) => setFormData({ ...formData, attempt_limit: e.target.value })}
                    />
                    <small className="help-text">Maximum viva attempts allowed per student.</small>
                    {formErrors.attempt_limit && (
                      <span className="error-text">{formErrors.attempt_limit}</span>
                    )}
                  </div>

                  <div className="form-group flex-1 checkbox-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={formData.is_active}
                        onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      />
                      <span>Active (Accepting submissions)</span>
                    </label>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="assign-instructions">Special Instructions for Students</label>
                  <textarea
                    id="assign-instructions"
                    rows="3"
                    placeholder="e.g. Ensure microphone is tested before starting. 20-minute limit strictly enforced."
                    value={formData.instructions}
                    onChange={(e) => setFormData({ ...formData, instructions: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowFormModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={formSubmitting}
                >
                  {formSubmitting
                    ? 'Saving...'
                    : editingAssignmentId
                    ? 'Update Assignment'
                    : 'Create Assignment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Submissions Modal */}
      {submissionsModalAssignment && (
        <div className="modal-backdrop">
          <div className="modal-content modal-xl">
            <div className="modal-header">
              <div>
                <h3>Submissions: {submissionsModalAssignment.title}</h3>
                <p className="modal-subtitle">
                  Course: {submissionsModalAssignment.course_name} •{' '}
                  Assessment: {submissionsModalAssignment.assessment_title}
                </p>
              </div>
              <button
                className="btn-close"
                onClick={() => setSubmissionsModalAssignment(null)}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              {submissionsLoading ? (
                <div className="loading-state">
                  <p>Loading submission records...</p>
                </div>
              ) : !submissionsData ? (
                <div className="empty-state">
                  <p>Could not load submission data.</p>
                </div>
              ) : (
                <div>
                  {/* Summary row */}
                  <div className="stats-kpi-grid">
                    <div className="kpi-card">
                      <span className="kpi-label">Eligible Students</span>
                      <span className="kpi-value">{submissionsData.total_eligible_students}</span>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Total Attempts</span>
                      <span className="kpi-value">{submissionsData.total_submissions}</span>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Completed Sessions</span>
                      <span className="kpi-value text-success">{submissionsData.completed_count}</span>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Average Score</span>
                      <span className="kpi-value text-primary">
                        {submissionsData.average_score !== null
                          ? formatRatioPercent(submissionsData.average_score)
                          : '—'}
                      </span>
                    </div>
                  </div>

                  {submissionsData.submissions.length === 0 ? (
                    <div className="empty-state">
                      <p>No students have submitted an attempt for this assignment yet.</p>
                    </div>
                  ) : (
                    <div className="table-responsive">
                      <table className="custom-table">
                        <thead>
                          <tr>
                            <th>Student</th>
                            <th>Email</th>
                            <th>Status</th>
                            <th>Score</th>
                            <th>Started</th>
                            <th>Completed</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {submissionsData.submissions.map((sub) => (
                            <tr key={sub.session_id}>
                              <td><strong>{sub.student_name}</strong></td>
                              <td>{sub.student_email}</td>
                              <td>
                                <span className={`status-tag ${sub.status}`}>
                                  {sub.status}
                                </span>
                              </td>
                              <td>
                                {sub.score !== null && sub.score !== undefined ? (
                                  <strong>{formatRatioPercent(sub.score)}</strong>
                                ) : (
                                  <span className="text-muted">—</span>
                                )}
                              </td>
                              <td>{formatAssignmentDate(sub.created_at)}</td>
                              <td>{formatAssignmentDate(sub.completed_at, 'In Progress')}</td>
                              <td>
                                {onNavigate && (
                                  <button
                                    className="btn-sm btn-secondary"
                                    onClick={() => {
                                      setSubmissionsModalAssignment(null)
                                      onNavigate(`session-review/${sub.session_id}`)
                                    }}
                                  >
                                    Review
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
              )}
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setSubmissionsModalAssignment(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
