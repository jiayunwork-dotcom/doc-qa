<template>
  <div class="kb-detail-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="kb-title">{{ kb?.name }}</span>
        <el-tag v-if="kb" size="small" type="info">{{ kb.document_count }} 篇文档</el-tag>
      </div>
      <div class="nav-right">
        <el-button text @click="goToDebug">
          <el-icon><Bug /></el-icon> 检索调试
        </el-button>
        <el-button text @click="showSettings = true">
          <el-icon><Setting /></el-icon> 设置
        </el-button>
      </div>
    </div>

    <div class="main-content">
      <div class="doc-panel">
        <div class="panel-header">
          <span class="panel-title">文档管理</span>
          <el-button type="primary" size="small" :icon="Upload" @click="triggerUpload">上传文档</el-button>
          <input
            ref="fileInput"
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md,.markdown"
            style="display: none"
            @change="handleFileSelect"
          />
        </div>

        <div
          class="upload-dropzone"
          :class="{ 'is-dragover': isDragging }"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">拖拽文件到此处上传</div>
          <div class="upload-hint">支持 PDF / DOCX / TXT / Markdown，单文件最大 50MB</div>
        </div>

        <el-scrollbar class="doc-list">
          <el-empty v-if="!documentsLoading && documents.length === 0" description="暂无文档" :image-size="80" />
          <div v-for="doc in documents" :key="doc.id" class="doc-item">
            <div class="doc-item-left">
              <el-icon :class="getFileIconClass(doc.file_type)"><Document /></el-icon>
              <div class="doc-info">
                <div class="doc-name" :title="doc.filename">{{ doc.filename }}</div>
                <div class="doc-meta">
                  <span>{{ formatSize(doc.file_size) }}</span>
                  <span class="dot">·</span>
                  <span>{{ formatTime(doc.uploaded_at) }}</span>
                  <span class="dot">·</span>
                  <span>{{ doc.chunk_count }} 分块</span>
                </div>
              </div>
            </div>
            <div class="doc-item-right">
              <el-tag :type="getStatusType(doc.status)" size="small" v-if="uploadingTasks[doc.id]">
                {{ uploadingTasks[doc.id].message }} ({{ uploadingTasks[doc.id].progress }}%)
              </el-tag>
              <el-tag :type="getStatusType(doc.status)" size="small" v-else>
                {{ getStatusText(doc.status) }}
              </el-tag>
              <el-progress
                v-if="uploadingTasks[doc.id] && uploadingTasks[doc.id].status !== 'ready'"
                :percentage="uploadingTasks[doc.id].progress"
                :stroke-width="3"
                :show-text="false"
                style="width: 60px; margin-left: 8px;"
              />
              <el-button text type="danger" size="small" @click="confirmDeleteDoc(doc)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </el-scrollbar>
      </div>

      <div class="chat-panel">
        <div class="chat-header">
          <div class="chat-title">
            <el-icon><ChatDotRound /></el-icon>
            <span>智能问答</span>
          </div>
          <el-select v-model="currentConversationId" placeholder="选择会话" clearable size="small" style="width: 200px;" @change="loadConversation">
            <el-option
              v-for="conv in conversations"
              :key="conv.id"
              :label="conv.title"
              :value="conv.id"
            />
          </el-select>
          <el-button text size="small" @click="newConversation" v-if="currentConversationId">
            <el-icon><Plus /></el-icon> 新对话
          </el-button>
        </div>

        <el-scrollbar ref="chatScroll" class="chat-messages">
          <div class="welcome-box" v-if="messages.length === 0">
            <el-icon class="welcome-icon"><Reading /></el-icon>
            <h3>开始提问吧</h3>
            <p>基于知识库中的文档内容，我会为你提供准确的答案</p>
          </div>
          <div v-for="(msg, idx) in messages" :key="msg.id || idx" class="message-wrap" :class="msg.role">
            <div class="message-avatar">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else><Robot /></el-icon>
            </div>
            <div class="message-bubble">
              <template v-if="msg.role === 'user'">{{ msg.content }}</template>
              <template v-else>
                <div class="answer-text" v-html="renderAnswerWithLinks(msg.content)"></div>
                <div v-if="msg.sources && msg.sources.length > 0" class="source-cards">
                  <el-collapse>
                    <el-collapse-item
                      v-for="(src, sIdx) in msg.sources"
                      :key="src.chunk_id"
                      :name="src.chunk_id"
                    >
                      <template #title>
                        <span class="source-title">
                          <el-tag size="small" type="primary">[{{ sIdx + 1 }}]</el-tag>
                          <span class="source-name">{{ src.document_name }}</span>
                          <span class="source-meta" v-if="src.page_number">第{{ src.page_number }}页</span>
                          <span class="source-meta" v-else-if="src.paragraph_number">第{{ src.paragraph_number }}段</span>
                          <span class="source-score">得分: {{ src.score.toFixed(3) }}</span>
                        </span>
                      </template>
                      <div class="source-content">{{ src.content }}</div>
                    </el-collapse-item>
                  </el-collapse>
                </div>
              </template>
            </div>
          </div>
          <div v-if="isAsking" class="message-wrap assistant">
            <div class="message-avatar"><el-icon><Robot /></el-icon></div>
            <div class="message-bubble">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </el-scrollbar>

        <div class="chat-input-area">
          <el-input
            v-model="questionInput"
            type="textarea"
            :rows="2"
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
            resize="none"
            @keydown.enter.exact.prevent="sendQuestion"
            :disabled="isAsking"
          />
          <el-button
            type="primary"
            :icon="Promotion"
            :disabled="!questionInput.trim() || isAsking"
            @click="sendQuestion"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="showSettings" title="知识库设置" width="520px">
      <el-form :model="settingsForm" label-width="100px" ref="settingsFormRef">
        <el-form-item label="名称">
          <el-input v-model="settingsForm.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="settingsForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="分块策略">
          <el-select v-model="settingsForm.chunk_strategy" style="width: 100%">
            <el-option label="固定长度分块" value="fixed" />
            <el-option label="语义分段" value="semantic" />
            <el-option label="按标题层级" value="heading" />
          </el-select>
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="settingsForm.chunk_size" :min="100" :max="2000" :step="100" />
        </el-form-item>
        <el-form-item label="重叠大小">
          <el-input-number v-model="settingsForm.chunk_overlap" :min="0" :max="500" :step="50" />
        </el-form-item>
        <el-form-item label="检索Top-K">
          <el-input-number v-model="settingsForm.top_k" :min="5" :max="100" />
        </el-form-item>
        <el-form-item label="重排序">
          <el-switch v-model="settingsForm.enable_rerank" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSettings = false">取消</el-button>
        <el-button type="primary" @click="saveSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Bug, Setting, Upload, UploadFilled, Document, Delete,
  ChatDotRound, User, Robot, Reading, Plus, Promotion, MoreFilled
} from '@element-plus/icons-vue'
import {
  getKnowledgeBase, updateKnowledgeBase, listDocuments, uploadDocument,
  getTaskStatus, deleteDocument, askQuestion, listConversations, getConversationMessages, deleteConversation
} from '@/api'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.id)

const kb = ref(null)
const showSettings = ref(false)
const settingsFormRef = ref(null)
const settingsForm = reactive({})

const documents = ref([])
const documentsLoading = ref(false)
const fileInput = ref(null)
const isDragging = ref(false)
const uploadingTasks = reactive({})

const messages = ref([])
const questionInput = ref('')
const isAsking = ref(false)
const currentConversationId = ref(null)
const conversations = ref([])
const chatScroll = ref(null)

function formatSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024
    i++
  }
  return `${bytes.toFixed(1)} ${units[i]}`
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function getStatusText(status) {
  const map = {
    uploaded: '已上传',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '向量化中',
    ready: '就绪',
    error: '失败'
  }
  return map[status] || status
}

function getStatusType(status) {
  const map = {
    uploaded: 'info',
    parsing: 'warning',
    chunking: 'warning',
    embedding: 'warning',
    ready: 'success',
    error: 'danger'
  }
  return map[status] || 'info'
}

function getFileIconClass(type) {
  return `file-icon file-${type || 'default'}`
}

function goBack() {
  router.push('/knowledge-bases')
}

function goToDebug() {
  router.push(`/knowledge-bases/${kbId.value}/debug`)
}

async function loadKb() {
  kb.value = await getKnowledgeBase(kbId.value)
}

async function loadDocuments() {
  documentsLoading.value = true
  try {
    documents.value = await listDocuments(kbId.value)
  } finally {
    documentsLoading.value = false
  }
}

async function loadConversations() {
  conversations.value = await listConversations(kbId.value)
}

function triggerUpload() {
  fileInput.value?.click()
}

function handleFileSelect(e) {
  const files = Array.from(e.target.files || [])
  uploadFiles(files)
  e.target.value = ''
}

function handleDrop(e) {
  isDragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  uploadFiles(files)
}

async function uploadFiles(files) {
  for (const file of files) {
    try {
      const task = await uploadDocument(kbId.value, file)
      if (task.document_id) {
        uploadingTasks[task.document_id] = {
          task_id: task.task_id,
          status: task.status,
          progress: task.progress,
          message: task.message
        }
        pollTaskStatus(task.task_id, task.document_id)
      }
      ElMessage.success(`文件 ${file.name} 已开始处理`)
    } catch (e) {
      ElMessage.error(`文件 ${file.name} 上传失败`)
    }
  }
  await loadDocuments()
}

function pollTaskStatus(taskId, docId) {
  const poll = async () => {
    try {
      const task = await getTaskStatus(taskId)
      if (docId) {
        uploadingTasks[docId] = {
          task_id: task.task_id,
          status: task.status,
          progress: task.progress,
          message: task.message
        }
      }
      if (task.status === 'ready' || task.status === 'error') {
        await loadDocuments()
        delete uploadingTasks[docId]
        return
      }
      setTimeout(poll, 1500)
    } catch (e) {
      setTimeout(poll, 2000)
    }
  }
  poll()
}

async function confirmDeleteDoc(doc) {
  try {
    await ElMessageBox.confirm(`确定删除文档「${doc.filename}」吗？`, '删除确认', { type: 'warning' })
    await deleteDocument(doc.id)
    ElMessage.success('删除成功')
    loadDocuments()
  } catch (e) {}
}

function openSettings() {
  if (kb.value) {
    Object.assign(settingsForm, {
      name: kb.value.name,
      description: kb.value.description || '',
      chunk_strategy: kb.value.chunk_strategy,
      chunk_size: kb.value.chunk_size,
      chunk_overlap: kb.value.chunk_overlap,
      top_k: kb.value.top_k,
      enable_rerank: kb.value.enable_rerank
    })
  }
  showSettings.value = true
}

watch(showSettings, (val) => {
  if (val) openSettings()
})

async function saveSettings() {
  try {
    await updateKnowledgeBase(kbId.value, settingsForm)
    ElMessage.success('设置已保存')
    showSettings.value = false
    loadKb()
  } catch (e) {}
}

async function newConversation() {
  currentConversationId.value = null
  messages.value = []
}

async function loadConversation(convId) {
  if (!convId) {
    messages.value = []
    return
  }
  try {
    messages.value = await getConversationMessages(convId)
    scrollToBottom()
  } catch (e) {}
}

function renderAnswerWithLinks(text) {
  if (!text) return ''
  return text.replace(/\[(\d+)\]/g, (match, num) => {
    return `<span class="cite-tag" data-idx="${parseInt(num) - 1}">[${num}]</span>`
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (chatScroll.value) {
      const scrollbar = chatScroll.value
      if (scrollbar.setScrollTop) {
        scrollbar.setScrollTop(99999)
      }
    }
  })
}

async function sendQuestion() {
  const question = questionInput.value.trim()
  if (!question) return

  const userMsg = { role: 'user', content: question, id: `temp-${Date.now()}` }
  messages.value.push(userMsg)
  questionInput.value = ''
  isAsking.value = true
  scrollToBottom()

  try {
    const resp = await askQuestion({
      question,
      knowledge_base_id: kbId.value,
      conversation_id: currentConversationId.value || undefined
    })
    currentConversationId.value = resp.conversation_id
    messages.value.push({
      role: 'assistant',
      content: resp.answer,
      sources: resp.sources,
      id: `resp-${Date.now()}`
    })
    loadConversations()
  } catch (e) {
    ElMessage.error('提问失败')
  } finally {
    isAsking.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  await Promise.all([loadKb(), loadDocuments(), loadConversations()])
})
</script>

<style scoped>
.kb-detail-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.top-navbar {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}

.nav-left, .nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-right: 8px;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.doc-panel {
  width: 380px;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.upload-dropzone {
  margin: 16px;
  padding: 24px;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  text-align: center;
  transition: all 0.2s;
}

.upload-dropzone.is-dragover {
  border-color: #409eff;
  background: #ecf5ff;
}

.upload-icon {
  font-size: 32px;
  color: #c0c4cc;
  margin-bottom: 8px;
}

.upload-text {
  color: #606266;
  font-size: 13px;
  margin-bottom: 4px;
}

.upload-hint {
  color: #909399;
  font-size: 11px;
}

.doc-list {
  flex: 1;
  overflow: auto;
}

.doc-item {
  padding: 12px 16px;
  border-bottom: 1px solid #f5f5f5;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.doc-item:hover {
  background: #fafafa;
}

.doc-item-left {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  flex: 1;
  min-width: 0;
}

.file-icon {
  font-size: 24px;
  margin-top: 2px;
  color: #67c23a;
  flex-shrink: 0;
}

.file-pdf { color: #f56c6c; }
.file-docx { color: #409eff; }
.file-txt { color: #909399; }
.file-markdown { color: #67c23a; }

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.dot {
  margin: 0 4px;
}

.doc-item-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  min-width: 0;
}

.chat-header {
  height: 56px;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  flex-shrink: 0;
}

.chat-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.chat-messages {
  flex: 1;
  padding: 24px;
  overflow: auto;
  background: #fafbfc;
}

.welcome-box {
  text-align: center;
  padding: 80px 20px;
  color: #909399;
}

.welcome-icon {
  font-size: 64px;
  color: #409eff;
  margin-bottom: 16px;
}

.welcome-box h3 {
  font-size: 20px;
  color: #303133;
  margin-bottom: 8px;
}

.message-wrap {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.message-wrap.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message-wrap.user .message-avatar {
  background: #409eff;
  color: #fff;
}

.message-wrap.assistant .message-avatar {
  background: #67c23a;
  color: #fff;
}

.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

.message-wrap.user .message-bubble {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 4px;
}

.message-wrap.assistant .message-bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #ebeef5;
  border-top-left-radius: 4px;
}

.answer-text :deep(.cite-tag) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 4px;
  font-size: 11px;
  margin: 0 2px;
  cursor: pointer;
  transition: background 0.2s;
}

.answer-text :deep(.cite-tag:hover) {
  background: #d9ecff;
}

.source-cards {
  margin-top: 12px;
}

.source-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #303133;
}

.source-name {
  font-weight: 500;
}

.source-meta, .source-score {
  font-size: 11px;
  color: #909399;
  margin-left: 4px;
}

.source-content {
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;
  max-height: 300px;
  overflow: auto;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 4px;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #c0c4cc;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.chat-input-area {
  padding: 16px 20px;
  border-top: 1px solid #ebeef5;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: #fff;
}

.chat-input-area :deep(.el-textarea__inner) {
  padding: 10px 12px;
}
</style>
