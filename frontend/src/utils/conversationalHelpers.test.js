import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  getStudentDashboardGreeting,
  getVivaOpeningGreeting,
  getCompletionClosingMessage,
} from './conversationalHelpers.js'

describe('conversationalHelpers', () => {
  it('getStudentDashboardGreeting handles first-time and returning students', () => {
    // First time student (0 sessions)
    const firstGreeting = getStudentDashboardGreeting('Aarav Sharma', 0, 14)
    assert.ok(firstGreeting.includes('Welcome, Aarav!'))
    assert.ok(firstGreeting.includes("Don't worry about getting everything perfect"))

    // Morning greeting (< 12)
    const morningGreeting = getStudentDashboardGreeting('Priya Patel', 3, 9)
    assert.ok(morningGreeting.includes('Good morning, Priya!'))

    // Evening greeting (>= 17)
    const eveningGreeting = getStudentDashboardGreeting('Rohan Gupta', 5, 19)
    assert.ok(eveningGreeting.includes('Good evening, Rohan!'))

    // Fallback when name is empty
    const noNameGreeting = getStudentDashboardGreeting(null, 0, 10)
    assert.ok(noNameGreeting.includes('Welcome, there!'))
  })

  it('getVivaOpeningGreeting personalizes opening and respects assessment title', () => {
    // Practice opening with name
    const practiceGreeting = getVivaOpeningGreeting('Kavya Iyer', true)
    assert.ok(practiceGreeting.includes('Hey Kavya!'))
    assert.ok(practiceGreeting.includes('Take a breath, relax'))

    // Assessment opening
    const assessmentGreeting = getVivaOpeningGreeting('Devraj Roy', false, 'Operating Systems Midterm')
    assert.ok(assessmentGreeting.includes('Welcome to Operating Systems Midterm, Devraj.'))
    assert.ok(assessmentGreeting.includes('Take your time and answer in your own words.'))
  })

  it('getCompletionClosingMessage reflects score without false praise', () => {
    // Strong score
    const strongMsg = getCompletionClosingMessage(0.88, 'Aarav Sharma', 4)
    assert.ok(strongMsg.includes('Outstanding work, Aarav!'))
    assert.ok(strongMsg.includes('strong mastery'))

    // Moderate score
    const midMsg = getCompletionClosingMessage(0.62, 'Aarav Sharma', 4)
    assert.ok(midMsg.includes('Good session, Aarav!'))
    assert.ok(midMsg.includes('solid foundations'))

    // Struggling score (< 0.50): supportive without false praise
    const devMsg = getCompletionClosingMessage(0.40, 'Aarav Sharma', 4)
    assert.ok(devMsg.includes('Good work showing up and giving it your best try, Aarav.'))
    assert.ok(devMsg.includes('Review the suggestions below'))
    assert.ok(!devMsg.includes('Outstanding'))
    assert.ok(!devMsg.includes('strong mastery'))

    // Missing score or 0 answers
    const emptyMsg = getCompletionClosingMessage(null, 'Aarav', 0)
    assert.ok(emptyMsg.includes('That concludes our session, Aarav.'))
  })
})
