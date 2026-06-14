import request from '@/utils/request'

export function listKnowledgeBases() {
  return request.get('/api/knowledge-bases')
}

export function createKnowledgeBase(data) {
  return request.post('/api/knowledge-bases', data)
}

export function getKnowledgeBase(id) {
  return request.get(`/api/knowledge-bases/${id}`)
}

export function updateKnowledgeBase(id, data) {
  return request.put(`/api/knowledge-bases/${id}`, data)
}

export function deleteKnowledgeBase(id) {
  return request.delete(`/api/knowledge-bases/${id}`)
}

export function listDocuments(kbId) {
  return request.get(`/api/documents/knowledge-base/${kbId}`)
}

export function uploadDocument(kbId, file, onProgress) {
  const formData = new FormData()
  formData.append('kb_id', kbId)
  formData.append('file', file)
  return request.post('/api/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
  })
}

export function getTaskStatus(taskId) {
  return request.get(`/api/documents/task/${taskId}`)
}

export function deleteDocument(docId) {
  return request.delete(`/api/documents/${docId}`)
}

export function askQuestion(data) {
  return request.post('/api/ask', data)
}

export function searchDocuments(data) {
  return request.post('/api/search', data)
}

export function listConversations(kbId) {
  return request.get('/api/conversations', { params: { kb_id: kbId } })
}

export function getConversationMessages(convId) {
  return request.get(`/api/conversations/${convId}`)
}

export function deleteConversation(convId) {
  return request.delete(`/api/conversations/${convId}`)
}

export function submitFeedback(data) {
  return request.post('/api/feedbacks', data)
}

export function getFeedbackStats(kbId) {
  return request.get(`/api/feedbacks/stats/${kbId}`)
}

export function createCompareTask(data) {
  return request.post('/api/compare', data)
}

export function getCompareResult(taskId, includeIgnored = false) {
  return request.get(`/api/compare/task/${taskId}`, { params: { include_ignored: includeIgnored } })
}

export function addIgnorePair(data) {
  return request.post('/api/compare/ignore', data)
}

export function removeIgnorePair(taskId, chunkAId, chunkBId) {
  return request.delete(`/api/compare/ignore/${taskId}/${chunkAId}/${chunkBId}`)
}

export function listIgnorePairs(taskId) {
  return request.get(`/api/compare/ignore/list/${taskId}`)
}

export function exportComparePdf(taskId) {
  return request.get(`/api/compare/task/${taskId}/export-pdf`, {
    responseType: 'blob'
  })
}

export function createBatchCompare(data) {
  return request.post('/api/compare/batch', data)
}

export function getBatchCompareStatus(taskId) {
  return request.get(`/api/compare/batch/${taskId}`)
}

export function getBatchCompareOverview(taskId) {
  return request.get(`/api/compare/batch/${taskId}/overview`)
}
