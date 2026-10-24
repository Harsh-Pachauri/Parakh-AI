import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Register from './pages/Register'
import StudentDashboard from './pages/StudentDashboard'
import TeacherDashboard from './pages/TeacherDashboard'
import VivaScreen from './pages/VivaScreen'
import FeedbackReport from './pages/FeedbackReport'
import SessionReview from './pages/SessionReview'
import PlatformAdminDashboard from './pages/PlatformAdminDashboard'
import InstitutionAdminDashboard from './pages/InstitutionAdminDashboard'
import QuestionBank from './pages/QuestionBank'
import ConsentModal from './components/ConsentModal'
import './App.css'

function Workspace() {
  const { user, token, loading, logout } = useAuth()
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/')
  const [showConsent, setShowConsent] = useState(false)

  useEffect(() => {
    const handleHash = () => setRoute(window.location.hash.slice(1) || '/')
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  const navigate = (path) => {
    window.location.hash = path
    setRoute(path)
  }

  // Handle unauthorized/expired session redirection
  useEffect(() => {
    const handleUnauthorized = () => {
      logout()
      navigate('/login')
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [logout])

  if (loading) {
    return <div className="center-screen">Loading Parakh AI...</div>
  }

  if (!token) {
    if (route === '/signup') {
      return <Register navigate={navigate} />
    }
    return (
      <Login
        navigate={navigate}
        onSuccess={(u) =>
          navigate(
            u?.role === 'admin'
              ? '/admin'
              : u?.role === 'institution_admin'
              ? '/institution'
              : u?.role === 'teacher'
              ? '/teacher'
              : '/'
          )
        }
      />
    )
  }

  const isTeacher = user?.role === 'teacher'
  const isPlatformAdmin = user?.role === 'admin'
  const isInstitutionAdmin = user?.role === 'institution_admin'

  // Safety guard for route transitions
  const canAccessTeacher = isTeacher || isPlatformAdmin
  const canAccessPlatformAdmin = isPlatformAdmin
  const canAccessInstitutionAdmin = isInstitutionAdmin || isPlatformAdmin

  if (route.startsWith('/admin') && !canAccessPlatformAdmin) {
    navigate('/')
  }
  if (route.startsWith('/institution') && !canAccessInstitutionAdmin) {
    navigate('/')
  }
  if (route.startsWith('/questions') && !isTeacher) {
    navigate('/')
  }
  if (route.startsWith('/review') && !canAccessTeacher) {
    navigate('/')
  }
  if (route.startsWith('/teacher') && !canAccessTeacher) {
    navigate('/')
  }
  if (route === '/' && isTeacher) {
    navigate('/teacher')
  }
  if (route === '/' && isPlatformAdmin) {
    navigate('/admin')
  }
  if (route === '/' && isInstitutionAdmin) {
    navigate('/institution')
  }

  let content
  if (route.startsWith('/viva')) {
    const rawParam = route.split('/')[2] || ''
    const [cId, queryStr] = rawParam.split('?')
    const params = new URLSearchParams(queryStr || '')
    const topicId = params.get('topic')
    const assessmentId = params.get('assessment')
    const assignmentId = params.get('assignment')
    content = (
      <VivaScreen
        navigate={navigate}
        courseId={cId || null}
        topicId={topicId || null}
        assessmentId={assessmentId || null}
        assignmentId={assignmentId || null}
      />
    )
  } else if (route.startsWith('/report/')) {
    content = <FeedbackReport sessionId={route.split('/')[2]} navigate={navigate} />
  } else if (route.startsWith('/review/')) {
    content = <SessionReview sessionId={route.split('/')[2]} navigate={navigate} />
  } else if (route.startsWith('/admin') && isPlatformAdmin) {
    content = <PlatformAdminDashboard navigate={navigate} />
  } else if (route.startsWith('/institution') && isInstitutionAdmin) {
    content = <InstitutionAdminDashboard navigate={navigate} />
  } else if (route === '/questions' && isTeacher) {
    content = <QuestionBank />
  } else if (isTeacher) {
    content = <TeacherDashboard navigate={navigate} />
  } else if (isInstitutionAdmin) {
    content = <InstitutionAdminDashboard navigate={navigate} />
  } else if (isPlatformAdmin) {
    content = <PlatformAdminDashboard navigate={navigate} />
  } else {
    content = <StudentDashboard navigate={navigate} />
  }

  const defaultHome = isPlatformAdmin
    ? '/admin'
    : isInstitutionAdmin
    ? '/institution'
    : isTeacher
    ? '/teacher'
    : '/'

  return (
    <div className="app-shell">
      <nav className="site-nav">
        <span className="nav-brand" onClick={() => navigate(defaultHome)} style={{ cursor: 'pointer' }}>
          parakh<span className="nav-brand-ai">.ai</span>
          <span className="nav-brand-light">viva</span>
        </span>
        <nav aria-label="Primary">
          {isTeacher && (
            <>
              <button
                onClick={() => navigate('/teacher')}
              >
                Teacher Dashboard
              </button>
              <button
                onClick={() => navigate('/questions')}
              >
                Question Bank
              </button>
            </>
          )}
          {isPlatformAdmin && (
            <button
              onClick={() => navigate('/admin')}
            >
              Admin Workspace
            </button>
          )}
          {isInstitutionAdmin && (
            <button
              onClick={() => navigate('/institution')}
            >
              Institution Workspace
            </button>
          )}
        </nav>
        <div className="nav-user">
          <span className="user-email">{user?.email}</span>
          <span className="user-role-badge">{user?.role}</span>
          <button className="signout" onClick={() => setShowConsent(true)}>
            Privacy Consent
          </button>
          <button
            className="signout"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            Log Out
          </button>
        </div>
      </nav>
      {content}
      {showConsent && <ConsentModal onClose={() => setShowConsent(false)} />}
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Workspace />
    </AuthProvider>
  )
}
