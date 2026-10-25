import Brand from '../components/Brand'
import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'

export default function Register({ navigate }) {
  const { register } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await register({ full_name: fullName, email, password }); navigate('/') }
    catch (err) { setError(err.userMessage || 'Could not create your account. Please try again.') }
    finally { setBusy(false) }
  }
  return <main className="auth-layout"><div className="auth-aside"><Brand light stacked tagline size={52} /><p className="eyebrow">YOUR VOICE, YOUR GROWTH</p><h1>Practice until<br/>you feel ready.</h1><p>Build confidence explaining what you know in a private, voice-led practice viva.</p><div className="aside-note">Free local AI practice. Your camera stays on your device.</div></div><section className="auth-card"><p className="eyebrow">GET STARTED</p><h2>Create your account</h2><p className="muted">Student accounts are free to create.</p><form onSubmit={submit} className="form-stack"><label>Full name<input autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} required maxLength={255}/></label><label>Email address<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required/></label><label>Password<input type="password" autoComplete="new-password" minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required/></label>{error && <p className="error-text" role="alert">{error}</p>}<button className="button primary full" disabled={busy}>{busy ? 'Creating account…' : 'Create student account'}</button></form><p className="small-muted">Already registered? <button className="inline-link" onClick={() => navigate('/login')}>Sign in</button></p><p className="small-muted"><button className="inline-link" onClick={() => navigate('/')}>Back to home</button></p></section></main>
}
