import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import {
  SUPPORTED_DOC_EXTENSIONS,
  validateDocumentFile,
  formatDocumentStatus,
  formatFileSize,
} from '../utils/documentHelpers'

export default function DocumentManager({ course, onDocumentsChanged }) {
  const topics = course?.topics || []
  const [selectedTopicId, setSelectedTopicId] = useState(topics[0]?.id || '')
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [autoIndex, setAutoIndex] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [indexingId, setIndexingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [statusMessage, setStatusMessage] = useState(null)

  // Keep topic selection synced if topics change
  useEffect(() => {
    if (topics.length > 0 && (!selectedTopicId || !topics.some((t) => t.id === selectedTopicId))) {
      setSelectedTopicId(topics[0].id)
    }
  }, [topics, selectedTopicId])

  const loadDocuments = async (topicId) => {
    if (!topicId) {
      setDocuments([])
      return
    }
    setLoading(true)
    setStatusMessage(null)
    try {
      const res = await apiClient.get(`/api/topics/${topicId}/documents`)
      setDocuments(Array.isArray(res.data) ? res.data : [])
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err.userMessage || 'Failed to fetch uploaded documents for this topic.',
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedTopicId) {
      loadDocuments(selectedTopicId)
    }
  }, [selectedTopicId])

  const handleFileChange = (e) => {
    const file = e.target.files?.[0] || null
    if (!file) {
      setSelectedFile(null)
      return
    }

    const validation = validateDocumentFile(file)
    if (!validation.isValid) {
      setStatusMessage({ type: 'error', text: validation.error })
      e.target.value = ''
      setSelectedFile(null)
      return
    }

    setStatusMessage(null)
    setSelectedFile(file)
  }

  const handleUpload = async (e) => {
    e.preventDefault()
    if (!selectedFile || !selectedTopicId) return

    const validation = validateDocumentFile(selectedFile)
    if (!validation.isValid) {
      setStatusMessage({ type: 'error', text: validation.error })
      return
    }

    setUploading(true)
    setStatusMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const uploadRes = await apiClient.post(
        `/api/topics/${selectedTopicId}/documents`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      )

      const uploadedDoc = uploadRes.data
      let embedSuccess = false

      if (autoIndex && uploadedDoc?.id) {
        try {
          await apiClient.post(`/api/documents/${uploadedDoc.id}/embed`)
          embedSuccess = true
        } catch (embedErr) {
          console.warn('Auto-embedding warning:', embedErr)
        }
      }

      setStatusMessage({
        type: 'success',
        text: embedSuccess
          ? `"${selectedFile.name}" uploaded and indexed into FAISS vector store successfully!`
          : `"${selectedFile.name}" uploaded successfully.`,
      })

      // Reset file input
      setSelectedFile(null)
      const inputEl = document.getElementById('curriculum-file-input')
      if (inputEl) inputEl.value = ''

      await loadDocuments(selectedTopicId)
      if (onDocumentsChanged) onDocumentsChanged()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err.userMessage || 'Failed to upload curriculum document. Please check the file and try again.',
      })
    } finally {
      setUploading(false)
    }
  }

  const handleEmbed = async (docId, filename) => {
    setIndexingId(docId)
    setStatusMessage(null)
    try {
      await apiClient.post(`/api/documents/${docId}/embed`)
      setStatusMessage({
        type: 'success',
        text: `"${filename}" indexed successfully! Chunks are now active for RAG evaluation.`,
      })
      await loadDocuments(selectedTopicId)
      if (onDocumentsChanged) onDocumentsChanged()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err.userMessage || `Failed to index "${filename}".`,
      })
    } finally {
      setIndexingId(null)
    }
  }

  const handleDelete = async (docId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? This will remove its embeddings from the topic vector store.`)) {
      return
    }

    setDeletingId(docId)
    setStatusMessage(null)
    try {
      await apiClient.delete(`/api/documents/${docId}`)
      setStatusMessage({
        type: 'success',
        text: `"${filename}" removed successfully.`,
      })
      await loadDocuments(selectedTopicId)
      if (onDocumentsChanged) onDocumentsChanged()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err.userMessage || `Failed to delete "${filename}".`,
      })
    } finally {
      setDeletingId(null)
    }
  }

  if (topics.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '24px', textAlign: 'center' }}>
        <p className="muted">
          No topics exist for this course yet. Extract topics from the syllabus or create topics above before uploading curriculum reference documents.
        </p>
      </div>
    )
  }

  return (
    <div className="document-manager-card" aria-label="Curriculum document management">
      <div className="section-heading">
        <div>
          <p className="eyebrow">RAG CURRICULUM INGESTION</p>
          <h3>Reference Documents & Course Materials</h3>
        </div>
        <label className="filter-label" style={{ minWidth: '220px' }}>
          Target Topic
          <select
            value={selectedTopicId}
            onChange={(e) => setSelectedTopicId(e.target.value)}
            disabled={uploading || !!indexingId}
          >
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {statusMessage && (
        <div
          className={`feedback-banner ${
            statusMessage.type === 'error' ? 'banner-error' : 'banner-success'
          }`}
          style={{ marginBottom: '16px' }}
        >
          {statusMessage.text}
        </div>
      )}

      {/* Upload Box */}
      <form className="document-upload-box" onSubmit={handleUpload}>
        <div className="upload-dropzone">
          <label htmlFor="curriculum-file-input" className="file-selector-label">
            <strong>Choose file</strong> or drag here:
            <input
              id="curriculum-file-input"
              type="file"
              accept={SUPPORTED_DOC_EXTENSIONS.join(',')}
              onChange={handleFileChange}
              disabled={uploading}
            />
          </label>
          <span className="file-info-muted">
            Supported: PDF, TXT, Markdown, CSV, JSON (max 25 MB)
          </span>
          {selectedFile && (
            <div className="selected-file-preview">
              <span>
                Selected: <strong>{selectedFile.name}</strong> ({formatFileSize(selectedFile.size)})
              </span>
            </div>
          )}
        </div>

        <div className="upload-controls">
          <label className="checkbox-label" title="Automatically chunk and create vector embeddings with FAISS after upload">
            <input
              type="checkbox"
              checked={autoIndex}
              onChange={(e) => setAutoIndex(e.target.checked)}
              disabled={uploading}
            />
            Auto-index for RAG (FAISS)
          </label>

          <button
            type="submit"
            className="button primary"
            disabled={!selectedFile || uploading}
          >
            {uploading ? 'Uploading & Indexing…' : 'Upload Document'}
          </button>
        </div>
      </form>

      {/* Document List */}
      <div className="documents-list-section" style={{ marginTop: '20px' }}>
        <h4>Uploaded Materials for Selected Topic</h4>
        {loading ? (
          <p className="muted" style={{ padding: '12px 0' }}>Loading documents…</p>
        ) : documents.length === 0 ? (
          <div className="empty-substate" style={{ padding: '16px', background: '#faf8f5', borderRadius: '6px', textAlign: 'center' }}>
            <p className="muted" style={{ margin: 0 }}>
              No reference materials uploaded for this topic yet. Upload lecture notes or textbook excerpts above to empower the AI viva examiner with ground-truth curriculum facts.
            </p>
          </div>
        ) : (
          <div className="table-responsive" style={{ marginTop: '10px' }}>
            <table className="data-table documents-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Chunks</th>
                  <th>Uploaded</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const statusInfo = formatDocumentStatus(doc.status)
                  const isUploadedPending = String(doc.status).toLowerCase() === 'uploaded'
                  const isIndexing = indexingId === doc.id
                  const isDeleting = deletingId === doc.id

                  return (
                    <tr key={doc.id}>
                      <td style={{ fontWeight: 500 }}>{doc.filename}</td>
                      <td>
                        <span className={`status-pill ${statusInfo.badgeClass}`}>
                          {statusInfo.label}
                        </span>
                      </td>
                      <td>{doc.chunk_count > 0 ? `${doc.chunk_count} chunks` : '—'}</td>
                      <td>
                        {doc.created_at
                          ? new Date(doc.created_at).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                            })
                          : '—'}
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {isUploadedPending && (
                          <button
                            type="button"
                            className="button secondary button-small"
                            onClick={() => handleEmbed(doc.id, doc.filename)}
                            disabled={isIndexing || isDeleting}
                            style={{ marginRight: '8px' }}
                          >
                            {isIndexing ? 'Indexing…' : 'Index (FAISS)'}
                          </button>
                        )}
                        <button
                          type="button"
                          className="button danger button-small"
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          disabled={isIndexing || isDeleting}
                        >
                          {isDeleting ? 'Deleting…' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
