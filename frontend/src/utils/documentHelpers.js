/**
 * Document helpers for teacher curriculum upload and RAG indexing.
 */

export const SUPPORTED_DOC_EXTENSIONS = ['.pdf', '.txt', '.md', '.csv', '.json']
export const MAX_DOC_SIZE_BYTES = 25 * 1024 * 1024 // 25 MB

/**
 * Validate an upload file for curriculum document ingestion.
 *
 * @param {File | { name: string, size: number } | null | undefined} file
 * @param {number} [maxBytes=MAX_DOC_SIZE_BYTES]
 * @returns {{ isValid: boolean, error: string | null }}
 */
export function validateDocumentFile(file, maxBytes = MAX_DOC_SIZE_BYTES) {
  if (!file || !file.name) {
    return { isValid: false, error: 'Please select a document file to upload.' }
  }

  const name = String(file.name).trim().toLowerCase()
  const hasValidExt = SUPPORTED_DOC_EXTENSIONS.some((ext) => name.endsWith(ext))
  if (!hasValidExt) {
    return {
      isValid: false,
      error: `Unsupported file type. Please upload a file in: ${SUPPORTED_DOC_EXTENSIONS.join(', ')}`,
    }
  }

  const size = Number(file.size) || 0
  if (size <= 0) {
    return { isValid: false, error: 'The selected file is empty.' }
  }

  if (size > maxBytes) {
    const maxMb = Math.round(maxBytes / (1024 * 1024))
    return {
      isValid: false,
      error: `File size exceeds the maximum allowed limit of ${maxMb}MB.`,
    }
  }

  return { isValid: true, error: null }
}

/**
 * Format document status into human-friendly badge properties.
 *
 * @param {string | null | undefined} status
 * @returns {{ label: string, badgeClass: string }}
 */
export function formatDocumentStatus(status) {
  const norm = String(status || '').toLowerCase()
  switch (norm) {
    case 'embedded':
      return { label: 'Indexed (RAG Ready)', badgeClass: 'badge-ready' }
    case 'uploaded':
      return { label: 'Uploaded (Pending Index)', badgeClass: 'badge-pending' }
    case 'failed':
      return { label: 'Index Failed', badgeClass: 'badge-failed' }
    default:
      return { label: status || 'Unknown', badgeClass: 'badge-neutral' }
  }
}

/**
 * Format raw byte size into human-readable string.
 *
 * @param {number | null | undefined} bytes
 * @returns {string}
 */
export function formatFileSize(bytes) {
  const num = Number(bytes)
  if (!num || num <= 0) return '0 B'
  if (num < 1024) return `${num} B`
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`
  return `${(num / (1024 * 1024)).toFixed(1)} MB`
}
