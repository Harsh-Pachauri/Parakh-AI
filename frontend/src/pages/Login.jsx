import Brand from '../components/Brand'
import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'

export default function Login({ navigate }) {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { const user = await login(email, password); navigate(user.role === 'admin' ? '/admin' : (user.role === 'institution_admin' ? '/institution' : (user.role === 'teacher' ? '/teacher' : '/'))) }
    catch (err) { setError(err.userMessage || 'Unable to sign in. Check your details and try again.') }
    finally { setBusy(false) }
  }
  return <main className="auth-layout"><div className="auth-aside"><Brand light stacked tagline size={52} /><p className="eyebrow">AI VIVA VOCE</p><h1>Think clearly.<br/>Speak confidently.</h1><p>Practice oral exams with thoughtful feedback, grounded in your course material.</p><div className="aside-note">A practice partner for the moments that matter.</div></div><section className="auth-card"><p className="eyebrow">Welcome back</p><h2>Sign in to Viva</h2><p className="muted">Use your student or teacher account to continue.</p><form onSubmit={submit} className="form-stack"><label>Email address<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>{error && <p className="error-text" role="alert">{error}</p>}<button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form><p className="small-muted">New to Viva? <button className="inline-link" onClick={() => navigate('/signup')}>Create a student account</button></p><p className="small-muted"><button className="inline-link" onClick={() => navigate('/')}>Back to home</button></p></section></main>
}
