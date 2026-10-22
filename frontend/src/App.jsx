import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import StudentDashboard from './pages/StudentDashboard'
import TeacherDashboard from './pages/TeacherDashboard'
import VivaScreen from './pages/VivaScreen'
import FeedbackReport from './pages/FeedbackReport'
import SessionReview from './pages/SessionReview'
import QuestionBank from './pages/QuestionBank'
import Landing from './pages/Landing'
import Register from './pages/Register'
import './App.css'
import './call.css'

function Workspace() {
  const { user, isAuthenticated, loading, logout } = useAuth(); const [route, setRoute] = useState(window.location.hash.slice(1) || '/')
  const navigate = (path) => { window.location.hash = path }
  useEffect(() => { const change = () => setRoute(window.location.hash.slice(1) || '/'); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change) }, [])
  if (loading) return <main className="loading-screen"><span className="spinner"/> Restoring your session…</main>
  if (!isAuthenticated) {
    if (route === '/login') return <Login navigate={navigate}/>
    if (route === '/signup') return <Register navigate={navigate}/>
    return <Landing navigate={navigate}/>
  }
  const teacher = user?.role === 'teacher' || user?.role === 'admin'
  if (!teacher && route.startsWith('/teacher')) navigate('/')
  if (teacher && route === '/') navigate('/teacher')
  let content
  if (route.startsWith('/viva')) content = <VivaScreen navigate={navigate} courseId={route.split('/')[2]}/>
  else if (route.startsWith('/report/')) content = <FeedbackReport sessionId={route.split('/')[2]} navigate={navigate}/>
  else if (route.startsWith('/review/')) content = <SessionReview sessionId={route.split('/')[2]} navigate={navigate}/>
  else if (route === '/questions' && teacher) content = <QuestionBank/>
  else if (teacher) content = <TeacherDashboard navigate={navigate}/>
  else content = <StudentDashboard navigate={navigate}/>
  return <><header className="site-nav"><button className="nav-brand" onClick={() => navigate(teacher?'/teacher':'/')}><span className="brand-mark small">V<span>.</span></span><span>viva<span className="nav-brand-light">practice</span></span></button><nav aria-label="Main navigation"><button onClick={() => navigate(teacher?'/teacher':'/')}>{teacher?'Sessions':'My courses'}</button>{teacher && <button onClick={() => navigate('/questions')}>Question bank</button>}</nav><div className="nav-user"><span>{user?.full_name}</span><button className="signout" onClick={() => { logout(); navigate('/login') }}>Sign out</button></div></header>{content}</>
}
export default function App() { return <AuthProvider><Workspace/></AuthProvider> }
