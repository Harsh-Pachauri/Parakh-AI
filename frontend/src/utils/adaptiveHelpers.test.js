import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  formatDifficultyBadge,
  formatDifficultyProgression,
  isAdaptiveSession,
  summarizeAdaptiveProgress,
  buildAdaptivePracticeUrl,
} from './adaptiveHelpers.js'

describe('adaptiveHelpers', () => {
  it('formatDifficultyBadge returns appropriate styling and labels', () => {
    assert.deepEqual(formatDifficultyBadge('easy'), {
      label: 'Foundational (Easy)',
      colorClass: 'diff-tag easy',
    })
    assert.deepEqual(formatDifficultyBadge('medium'), {
      label: 'Intermediate (Medium)',
      colorClass: 'diff-tag medium',
    })
    assert.deepEqual(formatDifficultyBadge('hard'), {
      label: 'Advanced (Hard)',
      colorClass: 'diff-tag hard',
    })
    assert.deepEqual(formatDifficultyBadge(null), {
      label: 'Intermediate (Medium)',
      colorClass: 'diff-tag medium',
    })
  })

  it('formatDifficultyProgression formats list of levels into numbered steps', () => {
    const progression = ['easy', 'medium', 'hard']
    const result = formatDifficultyProgression(progression)
    assert.equal(result.length, 3)
    assert.equal(result[0].step, 1)
    assert.equal(result[0].label, 'Easy')
    assert.equal(result[2].step, 3)
    assert.equal(result[2].label, 'Hard')

    // Empty list fallback
    const emptyResult = formatDifficultyProgression([])
    assert.equal(emptyResult.length, 1)
    assert.equal(emptyResult[0].label, 'Medium')
  })

  it('isAdaptiveSession distinguishes adaptive practice from fixed assessments', () => {
    assert.equal(isAdaptiveSession({ is_adaptive: true }), true)
    assert.equal(isAdaptiveSession({ is_adaptive: false }), false)
    assert.equal(isAdaptiveSession({ assessment_id: '123' }), false)
    assert.equal(isAdaptiveSession({ assignment_id: '456' }), false)
    assert.equal(isAdaptiveSession({}), true) // standard practice defaults to true
  })

  it('summarizeAdaptiveProgress accurately summarizes takeaways', () => {
    const summaryWithImprovement = {
      topics_showing_improvement: [{ topic_name: 'Indexing' }],
      topics_needing_attention: [],
    }
    const res1 = summarizeAdaptiveProgress(summaryWithImprovement)
    assert.equal(res1.hasImprovement, true)
    assert.equal(res1.improvedCount, 1)
    assert.ok(res1.note.includes('Demonstrated notable concept mastery improvement'))

    const summaryWithAttention = {
      topics_showing_improvement: [],
      topics_needing_attention: [{ topic_name: 'Concurrency' }],
    }
    const res2 = summarizeAdaptiveProgress(summaryWithAttention)
    assert.equal(res2.hasImprovement, false)
    assert.equal(res2.attentionCount, 1)
    assert.ok(res2.note.includes('Identified 1 area for targeted revision'))

    const summaryWithNote = {
      insufficient_data_note: 'Not enough repeat turns.',
    }
    const res3 = summarizeAdaptiveProgress(summaryWithNote)
    assert.equal(res3.note, 'Not enough repeat turns.')
  })

  it('buildAdaptivePracticeUrl constructs valid adaptive viva route', () => {
    assert.equal(buildAdaptivePracticeUrl('course-1'), '/viva/course-1?mode=adaptive')
    assert.equal(
      buildAdaptivePracticeUrl('course-1', 'topic-9'),
      '/viva/course-1?topic=topic-9&mode=adaptive'
    )
    assert.equal(buildAdaptivePracticeUrl(null), '/')
  })
})
