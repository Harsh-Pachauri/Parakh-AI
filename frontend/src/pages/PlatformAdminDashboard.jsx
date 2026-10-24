import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import {
  validateInstitutionForm,
  validateInstitutionAdminForm,
  formatPlatformAdminError,
  filterInstitutions,
} from '../utils/platformAdminHelpers'
import { formatTeacherDate } from '../utils/institutionHelpers'
import '../teacher-tools.css'

const blankInstitutionForm = {
  name: '',
  code: '',
}

const blankAdminForm = {
  institution_id: '',
  full_name: '',
  email: '',
  password: '',
}

export default function PlatformAdminDashboard({ navigate }) {
  const [institutions, setInstitutions] = useState([])
  const [institutionForm, setInstitutionForm] = useState(blankInstitutionForm)
  const [adminForm, setAdminForm] = useState(blankAdminForm)
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [submittingInst, setSubmittingInst] = useState(false)
  const [submittingAdmin, setSubmittingAdmin] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const fetchInstitutions = async () => {
    try {
      const response = await apiClient.get('/api/admin/institutions')
      setInstitutions(response.data)
      setError('')
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      setError(formatPlatformAdminError(cause))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInstitutions()
  }, [])

  const handleCreateInstitution = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')

    const validation = validateInstitutionForm(institutionForm)
    if (!validation.isValid) {
      setError(validation.error)
      return
    }

    setSubmittingInst(true)
    try {
      const response = await apiClient.post('/api/admin/institutions', {
        name: institutionForm.name.trim(),
        code: institutionForm.code.trim().toUpperCase(),
      })
      setNotice(`Institution "${response.data.name}" (${response.data.code}) created successfully.`)
      setInstitutionForm(blankInstitutionForm)
      // Auto-select this newly created institution in the admin appointment form
      setAdminForm((prev) => ({ ...prev, institution_id: response.data.id }))
      await fetchInstitutions()
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      setError(formatPlatformAdminError(cause, 'institution'))
    } finally {
      setSubmittingInst(false)
    }
  }

  const handleAppointAdmin = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')

    const validation = validateInstitutionAdminForm(adminForm)
    if (!validation.isValid) {
      setError(validation.error)
      return
    }

    setSubmittingAdmin(true)
    try {
      const response = await apiClient.post(
        `/api/admin/institutions/${adminForm.institution_id}/admins`,
        {
          full_name: adminForm.full_name.trim(),
          email: adminForm.email.trim(),
          password: adminForm.password,
        }
      )
      const selectedInst = institutions.find((i) => i.id === adminForm.institution_id)
      const instName = selectedInst ? selectedInst.name : 'the selected institution'
      setNotice(
        `Administrator "${response.data.full_name}" (${response.data.email}) appointed for ${instName}.`
      )
      setAdminForm(blankAdminForm)
    } catch (cause) {
      if (cause.response?.status === 401) {
        setError('Your session has expired. Please sign in again.')
        navigate?.('/login')
        return
      }
      setError(formatPlatformAdminError(cause, 'admin'))
    } finally {
      setSubmittingAdmin(false)
    }
  }

  const selectForAdminAppointment = (institutionId) => {
    setAdminForm((prev) => ({ ...prev, institution_id: institutionId }))
    setError('')
    const target = document.getElementById('appoint-admin-section')
    if (target) {
      target.scrollIntoView({ behavior: 'smooth' })
    }
  }

  const filteredInstitutions = filterInstitutions(institutions, searchQuery)

  return (
    <main className="page-shell">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">PLATFORM ADMINISTRATION</p>
          <h1>Institutions & Access</h1>
          <p className="muted">
            Manage participating institutions and appoint institution administrators.
          </p>
        </div>
        <button
          className="button secondary"
          type="button"
          onClick={() => {
            setLoading(true)
            fetchInstitutions()
          }}
          disabled={loading || submittingInst || submittingAdmin}
        >
          ↻ Refresh institutions
        </button>
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

      {/* Section 1: Create an Institution */}
      <section className="table-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">NEW INSTITUTION</p>
            <h2>Create an institution</h2>
          </div>
        </div>

        <form className="question-form" onSubmit={handleCreateInstitution} noValidate>
          <div className="form-grid">
            <label>
              Institution full name
              <input
                required
                maxLength={255}
                placeholder="e.g. St. Xavier's University"
                value={institutionForm.name}
                onChange={(e) => {
                  setInstitutionForm({ ...institutionForm, name: e.target.value })
                  if (error) setError('')
                }}
                disabled={submittingInst}
              />
            </label>
            <label>
              Short code / Acronym
              <input
                required
                maxLength={50}
                placeholder="e.g. SXU"
                value={institutionForm.code}
                onChange={(e) => {
                  setInstitutionForm({ ...institutionForm, code: e.target.value.toUpperCase() })
                  if (error) setError('')
                }}
                disabled={submittingInst}
              />
            </label>
          </div>

          <div className="row-actions">
            <button className="button primary" type="submit" disabled={submittingInst}>
              {submittingInst ? 'Creating institution…' : 'Create institution'}
            </button>
          </div>
        </form>
      </section>

      {/* Section 2: Appoint an Institution Administrator */}
      <section className="table-card" id="appoint-admin-section" style={{ marginTop: '24px' }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">ADMINISTRATIVE ACCESS</p>
            <h2>Appoint institution administrator</h2>
          </div>
        </div>

        <form className="question-form" onSubmit={handleAppointAdmin} noValidate>
          <div className="form-grid">
            <label>
              Target institution
              <select
                required
                value={adminForm.institution_id}
                onChange={(e) => {
                  setAdminForm({ ...adminForm, institution_id: e.target.value })
                  if (error) setError('')
                }}
                disabled={submittingAdmin}
              >
                <option value="">Select an institution…</option>
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.name} ({inst.code})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Admin full name
              <input
                required
                maxLength={255}
                placeholder="e.g. Dr. Priya Provost"
                value={adminForm.full_name}
                onChange={(e) => {
                  setAdminForm({ ...adminForm, full_name: e.target.value })
                  if (error) setError('')
                }}
                disabled={submittingAdmin}
              />
            </label>
            <label>
              Admin email address
              <input
                type="email"
                required
                maxLength={255}
                placeholder="provost@institution.edu"
                value={adminForm.email}
                onChange={(e) => {
                  setAdminForm({ ...adminForm, email: e.target.value })
                  if (error) setError('')
                }}
                disabled={submittingAdmin}
              />
            </label>
            <label>
              Initial temporary password
              <input
                type="password"
                required
                minLength={6}
                placeholder="Minimum 6 characters"
                value={adminForm.password}
                onChange={(e) => {
                  setAdminForm({ ...adminForm, password: e.target.value })
                  if (error) setError('')
                }}
                disabled={submittingAdmin}
              />
            </label>
          </div>

          <div className="row-actions">
            <button className="button primary" type="submit" disabled={submittingAdmin}>
              {submittingAdmin ? 'Appointing administrator…' : 'Appoint administrator'}
            </button>
          </div>
        </form>
      </section>

      {/* Section 3: Institutions Directory */}
      <section className="table-card recent-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DIRECTORY</p>
            <h2>Registered institutions</h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <input
              type="search"
              aria-label="Search institutions"
              placeholder="Search by name or code…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                border: '1px solid #dbdad5',
                borderRadius: '6px',
                padding: '7px 12px',
                background: '#fff',
                color: '#252a30',
                fontSize: '13px',
                width: '220px',
              }}
            />
            <span className="count-pill">
              {searchQuery.trim()
                ? `${filteredInstitutions.length} of ${institutions.length}`
                : `${institutions.length} ${institutions.length === 1 ? 'Institution' : 'Institutions'}`}
            </span>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading institutions…</p>
        ) : institutions.length === 0 ? (
          <div className="empty-state">
            <h3>No institutions registered</h3>
            <p>Create your first institution using the form above.</p>
          </div>
        ) : filteredInstitutions.length === 0 ? (
          <div className="empty-state">
            <h3>No matching institutions</h3>
            <p>No institutions match "{searchQuery}".</p>
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
            {filteredInstitutions.map((inst) => (
              <div className="session-row" key={inst.id}>
                <div>
                  <strong>{inst.name}</strong>
                  <span>
                    Code: <strong>{inst.code}</strong> · Added {formatTeacherDate(inst.created_at)}
                  </span>
                </div>
                <span className={`status-tag ${inst.is_active ? 'completed' : 'in_progress'}`}>
                  {inst.is_active ? 'active' : 'inactive'}
                </span>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => selectForAdminAppointment(inst.id)}
                >
                  + Appoint admin
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
