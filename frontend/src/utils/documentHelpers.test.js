import test from 'node:test'
import assert from 'node:assert/strict'
import {
  SUPPORTED_DOC_EXTENSIONS,
  validateDocumentFile,
  formatDocumentStatus,
  formatFileSize,
} from './documentHelpers.js'

test('documentHelpers - validateDocumentFile accepts valid files', () => {
  for (const ext of SUPPORTED_DOC_EXTENSIONS) {
    const file = { name: `lecture_notes${ext}`, size: 1024 * 100 }
    const result = validateDocumentFile(file)
    assert.equal(result.isValid, true)
    assert.equal(result.error, null)
  }
})

test('documentHelpers - validateDocumentFile rejects invalid extensions and empty files', () => {
  // Missing file
  assert.equal(validateDocumentFile(null).isValid, false)
  assert.equal(validateDocumentFile(undefined).isValid, false)

  // Invalid extensions
  assert.equal(validateDocumentFile({ name: 'malware.exe', size: 1000 }).isValid, false)
  assert.equal(validateDocumentFile({ name: 'archive.zip', size: 1000 }).isValid, false)
  assert.equal(validateDocumentFile({ name: 'photo.png', size: 1000 }).isValid, false)

  // Empty file (0 bytes)
  const emptyRes = validateDocumentFile({ name: 'notes.txt', size: 0 })
  assert.equal(emptyRes.isValid, false)
  assert.match(emptyRes.error, /empty/i)

  // Exceeds max bytes
  const largeRes = validateDocumentFile(
    { name: 'big_book.pdf', size: 30 * 1024 * 1024 },
    25 * 1024 * 1024
  )
  assert.equal(largeRes.isValid, false)
  assert.match(largeRes.error, /exceeds/i)
})

test('documentHelpers - formatDocumentStatus maps statuses accurately', () => {
  const embedded = formatDocumentStatus('embedded')
  assert.equal(embedded.label, 'Indexed (RAG Ready)')
  assert.equal(embedded.badgeClass, 'badge-ready')

  const uploaded = formatDocumentStatus('uploaded')
  assert.equal(uploaded.label, 'Uploaded (Pending Index)')
  assert.equal(uploaded.badgeClass, 'badge-pending')

  const failed = formatDocumentStatus('failed')
  assert.equal(failed.label, 'Index Failed')
  assert.equal(failed.badgeClass, 'badge-failed')

  const fallback = formatDocumentStatus('custom_state')
  assert.equal(fallback.label, 'custom_state')
  assert.equal(fallback.badgeClass, 'badge-neutral')
})

test('documentHelpers - formatFileSize formats bytes into friendly sizes', () => {
  assert.equal(formatFileSize(0), '0 B')
  assert.equal(formatFileSize(null), '0 B')
  assert.equal(formatFileSize(500), '500 B')
  assert.equal(formatFileSize(2048), '2.0 KB')
  assert.equal(formatFileSize(5 * 1024 * 1024), '5.0 MB')
})
