import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import {
  validateTeacherForm,
  formatTeacherDate,
  filterTeachers,
  formatTeacherRegistrationError,
} from '../utils/institutionHelpers'
import '../teacher-tools.css'

const blankForm = {
  full_name: '',
  email: '',
  password: '',
}

export default function InstitutionAdminDashboard({ navigate }) {
  const [institution, setInstitution] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [form, setForm] = useState(blankForm)
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const fetchInstitutionProfile = async () => {
    try {
      const response = await apiClient.get('/api/institution/profile')
      setInstitution(response.data)
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      // Non-critical profile load error
      console.warn('Could not load institution profile:', cause.userMessage)
    }
  }

  const fetchTeachers = async () => {
    try {
      const response = await apiClient.get('/api/institution/teachers')
      setTeachers(response.data)
      setError('')
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      setError(cause.userMessage || 'Could not load teachers.')
    } finally {
      setLoading(false)
    }
  }

  const refreshDashboard = async () => {
    setLoading(true)
    setError('')
    try {
      await Promise.allSettled([fetchInstitutionProfile(), fetchTeachers()])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshDashboard()
  }, [])

  const handleFormFieldChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    if (error) setError('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')

    const validation = validateTeacherForm(form)
    if (!validation.isValid) {
      setError(validation.error)
      return
    }

    setSubmitting(true)
    try {
      const response = await apiClient.post('/api/institution/teachers', {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      setNotice(
        `Teacher "${response.data.full_name}" (${response.data.email}) registered successfully. They can now sign in using their credentials.`
      )
      setForm(blankForm)
      await fetchTeachers()
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      setError(formatTeacherRegistrationError(cause, form.email))
    } finally {
      setSubmitting(false)
    }
  }

  const filteredTeachers = filterTeachers(teachers, searchQuery)

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">
            INSTITUTION WORKSPACE{institution?.code ? ` · ${institution.code}` : ''}
          </p>
          <h1>{institution?.name || 'Faculty Management'}</h1>
          <p className="muted">
            Register and manage teachers authorized to conduct oral exams for{' '}
            {institution?.name ? <strong>{institution.name}</strong> : 'your institution'}.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {institution?.code && (
            <span className="count-pill" title="Institution Short Code">
              Code: <strong>{institution.code}</strong>
            </span>
          )}
          <button
            className="button secondary"
            type="button"
            onClick={refreshDashboard}
            disabled={loading || submitting}
          >
            ↻ Refresh directory
          </button>
        </div>
      </div>

      {error && (
        <p className="error-text notice" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success-text notice" role="status">
          {notice}
        </p>
      )}

      <section className="table-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">NEW FACULTY</p>
            <h2>Register a teacher</h2>
          </div>
        </div>

        <form className="question-form" onSubmit={handleSubmit} noValidate>
          <div className="form-grid">
            <label>
              Full name
              <input
                required
                maxLength={255}
                placeholder="e.g. Dr. Priya Sharma"
                value={form.full_name}
                onChange={(e) => handleFormFieldChange('full_name', e.target.value)}
                disabled={submitting}
              />
            </label>
            <label>
              Email address
              <input
                type="email"
                required
                maxLength={255}
                placeholder="teacher@institution.edu"
                value={form.email}
                onChange={(e) => handleFormFieldChange('email', e.target.value)}
                disabled={submitting}
              />
            </label>
            <label>
              Initial password
              <input
                type="password"
                required
                minLength={6}
                placeholder="Minimum 6 characters"
                value={form.password}
                onChange={(e) => handleFormFieldChange('password', e.target.value)}
                disabled={submitting}
              />
            </label>
          </div>

          <div className="row-actions">
            <button className="button primary" type="submit" disabled={submitting}>
              {submitting ? 'Registering teacher…' : 'Register teacher'}
            </button>
          </div>
        </form>
      </section>

      <section className="table-card recent-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">FACULTY DIRECTORY</p>
            <h2>Registered teachers</h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <input
              type="search"
              aria-label="Search teachers"
              placeholder="Search by name or email…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                border: '1px solid #dbdad5',
                borderRadius: '6px',
                padding: '7px 12px',
                background: '#fff',
                color: '#252a30',
                fontSize: '13px',
                width: '210px',
              }}
            />
            <span className="count-pill">
              {searchQuery.trim()
                ? `${filteredTeachers.length} of ${teachers.length}`
                : `${teachers.length} ${teachers.length === 1 ? 'Teacher' : 'Teachers'}`}
            </span>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading teachers…</p>
        ) : teachers.length === 0 ? (
          <div className="empty-state">
            <h3>No teachers registered</h3>
            <p>Faculty members registered for your institution will appear here.</p>
          </div>
        ) : filteredTeachers.length === 0 ? (
          <div className="empty-state">
            <h3>No matching teachers</h3>
            <p>No faculty members match "{searchQuery}".</p>
            <button
              className="button secondary"
              type="button"
              onClick={() => setSearchQuery('')}
              style={{ marginTop: '12px' }}
            >
              Clear search
            </button>
          </div>
        ) : (
          <div className="session-list">
            {filteredTeachers.map((teacher) => (
              <div className="session-row" key={teacher.id}>
                <div>
                  <strong>{teacher.full_name}</strong>
                  <span>
                    {teacher.email} · Added {formatTeacherDate(teacher.created_at)}
                  </span>
                </div>
                <span className="status-tag completed">{teacher.role}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
