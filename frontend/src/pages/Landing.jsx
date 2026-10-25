import hero from '../assets/hero.png'
import Brand from '../components/Brand'

const FEATURES = [
  {
    icon: '🎙️',
    title: 'Speak naturally',
    text: 'Answer aloud with live speech recognition. The interviewer asks each question by voice, and a built-in microphone check makes sure you are heard.',
  },
  {
    icon: '🎯',
    title: 'Adaptive difficulty',
    text: 'Strong answers lead to harder follow-ups. Struggles bring in foundational ideas, so every session meets you where you are.',
  },
  {
    icon: '📚',
    title: 'Grounded in your course',
    text: 'Teachers upload lecture notes (PDF, TXT, Markdown, CSV, JSON). Answers are checked against that material using retrieval, not guesswork.',
  },
  {
    icon: '📊',
    title: 'Clear rubric feedback',
    text: 'Every answer is scored for correctness, completeness and clarity, with a plain-language explanation and a supportive closing summary.',
  },
  {
    icon: '🧭',
    title: 'Personal practice plan',
    text: 'See your strengths, the topics that need work, and recommended practice, built from everything you have answered so far.',
  },
  {
    icon: '📄',
    title: 'Reports you can keep',
    text: 'Download a clean PDF of your performance report. Teachers can export class results to CSV or PDF.',
  },
]

const ROLES = [
  {
    tag: 'Students',
    points: [
      'Practice any course or take assigned vivas',
      'Live voice conversation with an AI interviewer',
      'Scores, rubric and a personal weakness report',
    ],
    cta: 'Start practicing',
    to: '/signup',
  },
  {
    tag: 'Teachers',
    points: [
      'Build custom oral assessments from a question bank',
      'Schedule assignments with deadlines and attempt limits',
      'Class analytics, student history and score overrides',
    ],
    cta: 'Teacher sign in',
    to: '/login',
  },
  {
    tag: 'Institutions',
    points: [
      'A private workspace for your college',
      'Register and manage your faculty',
      'Your data stays inside your institution',
    ],
    cta: 'Institution sign in',
    to: '/login',
  },
  {
    tag: 'Platform admins',
    points: [
      'Onboard new institutions in minutes',
      'Appoint institution administrators',
      'One platform, many colleges',
    ],
    cta: 'Admin sign in',
    to: '/login',
  },
]

const STEPS = [
  { n: '01', title: 'Set up', text: 'An institution is created and teachers add courses, topics and reference material.' },
  { n: '02', title: 'Assign', text: 'Teachers publish an oral assessment and schedule it with a deadline.' },
  { n: '03', title: 'Speak', text: 'Students check their mic and talk through adaptive questions with the AI interviewer.' },
  { n: '04', title: 'Improve', text: 'Everyone gets scores, feedback and analytics, then practices where it matters.' },
]

export default function Landing({ navigate }) {
  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  return (
    <main className="landing-page">
      <header className="landing-nav">
        <Brand onClick={() => navigate('/')} />
        <nav>
          <button className="landing-link landing-anchor" onClick={() => scrollTo('features')}>
            Features
          </button>
          <button className="landing-link landing-anchor" onClick={() => scrollTo('roles')}>
            Who it's for
          </button>
          <button className="landing-link landing-anchor" onClick={() => scrollTo('how')}>
            How it works
          </button>
          <button className="landing-link" onClick={() => navigate('/login')}>
            Sign in
          </button>
          <button className="button primary" onClick={() => navigate('/signup')}>
            Get started
          </button>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow">PRACTICE OUT LOUD</p>
          <h1>
            Walk into your viva
            <br />
            <em>ready to speak.</em>
          </h1>
          <p className="landing-lead">
            A calm, voice-led practice interview that adapts to you, grounded in your own course material, with
            clear feedback for students and real tools for teachers and institutions.
          </p>
          <div className="landing-actions">
            <button className="button primary" onClick={() => navigate('/signup')}>
              Start practicing <span aria-hidden="true">→</span>
            </button>
            <button className="button secondary" onClick={() => navigate('/login')}>
              I already have an account
            </button>
          </div>
          <div className="landing-proof">
            <span>Voice-led</span>
            <i />
            <span>Adaptive questions</span>
            <i />
            <span>Camera preview stays private</span>
          </div>
        </div>
        <div className="landing-visual">
          <img src={hero} alt="A student preparing for a video viva practice session" />
          <div className="visual-card">
            <span className="live-dot" /> Practice at your own pace
          </div>
        </div>
      </section>

      <section id="features" className="landing-section">
        <p className="eyebrow">WHAT YOU GET</p>
        <h2 className="landing-h2">Everything for a better oral exam</h2>
        <div className="landing-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="landing-card">
              <span className="landing-icon" aria-hidden="true">
                {f.icon}
              </span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="roles" className="landing-section">
        <p className="eyebrow">BUILT FOR EVERY ROLE</p>
        <h2 className="landing-h2">One platform, four workspaces</h2>
        <div className="landing-grid landing-grid-4">
          {ROLES.map((r) => (
            <article key={r.tag} className="landing-card landing-role">
              <h3>{r.tag}</h3>
              <ul>
                {r.points.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
              <button className="text-button" onClick={() => navigate(r.to)}>
                {r.cta} →
              </button>
            </article>
          ))}
        </div>
      </section>

      <section id="how" className="landing-section">
        <p className="eyebrow">HOW IT WORKS</p>
        <h2 className="landing-h2">From setup to feedback in four steps</h2>
        <div className="landing-steps">
          {STEPS.map((s) => (
            <article key={s.n}>
              <span>{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>Ready to speak with confidence?</h2>
        <p>Create a student account and take your first practice viva in minutes.</p>
        <div className="landing-actions">
          <button className="button primary" onClick={() => navigate('/signup')}>
            Create a student account
          </button>
          <button className="button secondary" onClick={() => navigate('/login')}>
            Sign in
          </button>
        </div>
      </section>

      <footer className="landing-footer">
        <Brand size={30} tagline />
        <span>Scores are automated practice feedback for teacher review. Camera cues are approximate and never decide your score.</span>
      </footer>
    </main>
  )
}
