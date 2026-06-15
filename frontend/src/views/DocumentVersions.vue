<template>
  <div class="doc-versions-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="doc-title">{{ currentDoc?.filename || '文档版本' }}</span>
        <el-tag v-if="currentDoc" type="success" size="small" effect="light">
          v{{ currentDoc.version }} (当前激活)
        </el-tag>
      </div>
      <div class="nav-right">
        <el-button text @click="refreshData">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="main-tabs">
      <el-tab-pane label="版本历史" name="versions">
        <div class="versions-panel">
          <div class="compare-bar" v-if="versions.length >= 2">
            <el-alert
              title="选择两个版本进行差异对比"
              type="info"
              :closable="false"
              show-icon
              class="compare-alert"
            />
            <div class="compare-actions">
              <el-tag v-if="selectedCompareVersions.length > 0" type="primary" size="small">
                已选 {{ selectedCompareVersions.length }} 个
              </el-tag>
              <el-button
                type="primary"
                size="small"
                :disabled="selectedCompareVersions.length !== 2"
                @click="startCompare"
              >
                <el-icon><DataAnalysis /></el-icon> 对比差异
              </el-button>
              <el-button size="small" @click="clearCompareSelection" v-if="selectedCompareVersions.length > 0">
                清除选择
              </el-button>
            </div>
          </div>

          <el-empty v-if="loading" description="加载中..." :image-size="60" />
          <el-empty v-else-if="versions.length === 0" description="暂无版本记录" :image-size="80" />

          <div v-else class="versions-list">
            <div
              v-for="ver in sortedVersions"
              :key="ver.id"
              class="version-item"
              :class="{
                'is-active': ver.is_active,
                'is-selected': selectedCompareVersions.includes(ver.id)
              }"
              @click="toggleVersionSelection(ver)"
            >
              <div class="version-left">
                <el-checkbox
                  v-if="versions.length >= 2 && ver.status === 'ready'"
                  :model-value="selectedCompareVersions.includes(ver.id)"
                  @click.stop
                  @change="() => {}"
                  style="margin-right: 12px"
                />
                <div class="version-icon-wrap">
                  <div class="version-icon" :class="ver.is_active ? 'active' : ''">
                    <el-icon><Document /></el-icon>
                  </div>
                  <div class="version-line" v-if="ver !== sortedVersions[sortedVersions.length - 1]"></div>
                </div>
                <div class="version-info">
                  <div class="version-header">
                    <span class="version-label">v{{ ver.version }}</span>
                    <el-tag v-if="ver.is_active" type="success" size="small" effect="dark">
                      当前版本
                    </el-tag>
                    <el-tag v-if="ver.upload_remark" size="small" type="info">
                      {{ ver.upload_remark }}
                    </el-tag>
                    <el-tag :type="getStatusType(ver.status)" size="small">
                      {{ getStatusText(ver.status) }}
                    </el-tag>
                  </div>
                  <div class="version-meta">
                    <span>{{ formatSize(ver.file_size) }}</span>
                    <span class="dot">·</span>
                    <span>{{ formatTime(ver.uploaded_at) }}</span>
                    <span class="dot">·</span>
                    <span>{{ ver.chunk_count }} 分块</span>
                  </div>
                </div>
              </div>
              <div class="version-actions" @click.stop>
                <el-button size="small" @click="viewVersion(ver)" :disabled="ver.status !== 'ready'">
                  <el-icon><View /></el-icon> 查看
                </el-button>
                <el-button
                  size="small"
                  type="warning"
                  :disabled="ver.is_active || ver.status !== 'ready'"
                  @click="confirmRollback(ver)"
                >
                  <el-icon><RefreshLeft /></el-icon> 回退到此版本
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="差异对比" name="compare" v-if="compareResult">
        <div class="compare-panel">
          <div class="compare-header">
            <div class="compare-doc-info">
              <el-tag type="warning" size="large">旧版本 v{{ compareOldVersion }}</el-tag>
              <el-icon class="vs-icon"><ArrowRight /></el-icon>
              <el-tag type="success" size="large">新版本 v{{ compareNewVersion }}</el-tag>
            </div>
            <div class="compare-actions">
              <el-button type="primary" size="small" @click="exportDiffPdf">
                <el-icon><Download /></el-icon> 导出PDF报告
              </el-button>
              <el-button size="small" @click="closeCompare">
                关闭对比
              </el-button>
            </div>
          </div>

          <div class="compare-summary">
            <div class="summary-card">
              <div class="summary-value danger">{{ compareResult.summary?.unique_a_count || 0 }}</div>
              <div class="summary-label">已删除段落</div>
            </div>
            <div class="summary-card">
              <div class="summary-value success">{{ compareResult.summary?.unique_b_count || 0 }}</div>
              <div class="summary-label">已新增段落</div>
            </div>
            <div class="summary-card">
              <div class="summary-value warning">{{ compareResult.summary?.similar_count || 0 }}</div>
              <div class="summary-label">已修改段落</div>
            </div>
            <div class="summary-card">
              <div class="summary-value info">{{ compareResult.summary?.repeated_count || 0 }}</div>
              <div class="summary-label">未变化段落</div>
            </div>
          </div>

          <el-scrollbar class="compare-content">
            <div v-if="compareResult.unique_old?.length > 0" class="diff-section">
              <h4 class="section-title">
                <el-icon color="#f56c6c"><Minus /></el-icon>
                已删除内容（仅旧版本存在）
              </h4>
              <div
                v-for="(chunk, idx) in compareResult.unique_old"
                :key="'del-' + chunk.chunk_id"
                class="diff-chunk deleted"
              >
                <div class="chunk-header">第 {{ idx + 1 }} 条 · 分块 #{{ chunk.chunk_index + 1 }}</div>
                <div class="chunk-content">{{ chunk.content }}</div>
              </div>
            </div>

            <div v-if="compareResult.unique_new?.length > 0" class="diff-section">
              <h4 class="section-title">
                <el-icon color="#67c23a"><Plus /></el-icon>
                已新增内容（仅新版本存在）
              </h4>
              <div
                v-for="(chunk, idx) in compareResult.unique_new"
                :key="'add-' + chunk.chunk_id"
                class="diff-chunk added"
              >
                <div class="chunk-header">第 {{ idx + 1 }} 条 · 分块 #{{ chunk.chunk_index + 1 }}</div>
                <div class="chunk-content">{{ chunk.content }}</div>
              </div>
            </div>

            <div v-if="compareResult.similar_pairs?.length > 0" class="diff-section">
              <h4 class="section-title">
                <el-icon color="#e6a23c"><Edit /></el-icon>
                已修改内容（相似但有差异）
              </h4>
              <div
                v-for="(pair, idx) in compareResult.similar_pairs"
                :key="'mod-' + idx"
                class="diff-pair"
              >
                <div class="pair-header">
                  差异对 #{{ idx + 1 }} · 相似度 {{ (pair.similarity * 100).toFixed(1) }}%
                </div>
                <div class="pair-content">
                  <div class="pair-col old">
                    <div class="col-title">旧版本 v{{ compareOldVersion }} · 分块 #{{ pair.chunk_a?.chunk_index + 1 }}</div>
                    <div class="col-body diff-html" v-html="pair.diff_a"></div>
                  </div>
                  <div class="pair-col new">
                    <div class="col-title">新版本 v{{ compareNewVersion }} · 分块 #{{ pair.chunk_b?.chunk_index + 1 }}</div>
                    <div class="col-body diff-html" v-html="pair.diff_b"></div>
                  </div>
                </div>
              </div>
            </div>

            <el-empty v-if="!hasAnyDiff" description="两个版本内容完全相同，无差异" />
          </el-scrollbar>
        </div>
      </el-tab-pane>

      <el-tab-pane label="变更时间线" name="timeline">
        <div class="timeline-panel">
          <div class="timeline-filters">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              size="small"
              clearable
              @change="loadTimeline"
            />
            <el-select v-model="filterChangeType" placeholder="变更类型" size="small" clearable @change="loadTimeline">
              <el-option label="大幅修改" value="major" />
              <el-option label="小幅修改" value="minor" />
              <el-option label="格式调整" value="format" />
            </el-select>
            <el-button size="small" @click="loadTimeline">
              <el-icon><Search /></el-icon> 筛选
            </el-button>
            <el-button size="small" @click="resetFilters">重置</el-button>
          </div>

          <el-empty v-if="timelineLoading" description="加载中..." :image-size="60" />
          <el-empty v-else-if="timelineEvents.length === 0" description="暂无变更记录" :image-size="80" />

          <el-timeline v-else class="timeline-list">
            <el-timeline-item
              v-for="event in timelineEvents"
              :key="event.id"
              :timestamp="formatTime(event.created_at)"
              :type="getTimelineItemType(event)"
              :color="getTimelineItemColor(event)"
              size="large"
            >
              <div class="timeline-card" :class="{ 'is-rollback': event.event_type === 'rollback' }">
                <div class="timeline-header">
                  <span class="event-version">v{{ event.version }}</span>
                  <el-tag size="small" :type="event.event_type === 'rollback' ? 'warning' : 'primary'">
                    {{ event.event_type === 'rollback' ? '版本回退' : '版本上传' }}
                  </el-tag>
                  <el-tag size="small" :type="getChangeTypeTag(event.change_type)">
                    {{ getChangeTypeLabel(event.change_type) }}
                  </el-tag>
                </div>
                <div class="timeline-summary" v-if="event.event_type === 'rollback'">
                  <el-icon><RefreshLeft /></el-icon>
                  从 v{{ event.rollback_from_version }} 回退到 v{{ event.rollback_to_version }}
                </div>
                <div class="timeline-summary" v-else>
                  <span class="summary-item add" v-if="event.change_summary?.added > 0">
                    +{{ event.change_summary.added }} 新增
                  </span>
                  <span class="summary-item del" v-if="event.change_summary?.deleted > 0">
                    -{{ event.change_summary.deleted }} 删除
                  </span>
                  <span class="summary-item mod" v-if="event.change_summary?.modified > 0">
                    ~{{ event.change_summary.modified }} 修改
                  </span>
                  <span class="summary-item total">
                    共 {{ event.change_summary?.total_current || 0 }} 段
                  </span>
                </div>
                <div class="timeline-meta">
                  <span>{{ formatSize(event.file_size) }}</span>
                  <span class="dot">·</span>
                  <span>{{ event.upload_remark || '无备注' }}</span>
                </div>
                <div class="timeline-actions">
                  <el-button
                    type="primary"
                    size="small"
                    link
                    :disabled="!canViewDiff(event)"
                    @click="viewEventDiff(event)"
                  >
                    查看与上一版本差异
                  </el-button>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Refresh, Document, DataAnalysis, View, RefreshLeft,
  ArrowRight, Download, Minus, Plus, Edit, Search
} from '@element-plus/icons-vue'
import {
  listDocumentVersions, rollbackToVersion, getDocumentTimeline,
  compareVersions, exportVersionDiffPdf, getTaskStatus
} from '@/api'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.kbId)
const docId = computed(() => route.params.docId)

const versions = ref([])
const loading = ref(false)
const currentDoc = ref(null)
const activeTab = ref('versions')
const selectedCompareVersions = ref([])
const compareResult = ref(null)
const compareOldVersion = ref(1)
const compareNewVersion = ref(1)
const rollbackLoading = ref(false)
const compareLoading = ref(false)

const timelineEvents = ref([])
const timelineLoading = ref(false)
const dateRange = ref([])
const filterChangeType = ref('')

const sortedVersions = computed(() => {
  return [...versions.value].sort((a, b) => b.version - a.version)
})

const hasAnyDiff = computed(() => {
  if (!compareResult.value) return false
  return (
    (compareResult.value.unique_old?.length || 0) > 0 ||
    (compareResult.value.unique_new?.length || 0) > 0 ||
    (compareResult.value.similar_pairs?.length || 0) > 0
  )
})

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
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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

function goBack() {
  router.push(`/knowledge-bases/${kbId.value}`)
}

async function refreshData() {
  await Promise.all([loadVersions(), loadTimeline()])
}

async function loadVersions() {
  loading.value = true
  try {
    versions.value = await listDocumentVersions(docId.value)
    currentDoc.value = versions.value.find(v => v.is_active) || versions.value[0] || null
  } finally {
    loading.value = false
  }
}

async function loadTimeline() {
  timelineLoading.value = true
  try {
    const params = {}
    if (dateRange.value && dateRange.value.length === 2) {
      const start = dateRange.value[0]
      const end = dateRange.value[1]
      if (start) {
        const sd = start instanceof Date ? start : new Date(start)
        params.start_date = `${sd.getFullYear()}-${String(sd.getMonth() + 1).padStart(2, '0')}-${String(sd.getDate()).padStart(2, '0')}`
      }
      if (end) {
        const ed = end instanceof Date ? end : new Date(end)
        params.end_date = `${ed.getFullYear()}-${String(ed.getMonth() + 1).padStart(2, '0')}-${String(ed.getDate()).padStart(2, '0')}`
      }
    }
    if (filterChangeType.value) {
      params.change_type = filterChangeType.value
    }
    timelineEvents.value = await getDocumentTimeline(docId.value, params)
  } catch (e) {
    timelineEvents.value = []
  } finally {
    timelineLoading.value = false
  }
}

function resetFilters() {
  dateRange.value = []
  filterChangeType.value = ''
  loadTimeline()
}

function toggleVersionSelection(ver) {
  if (ver.status !== 'ready' || versions.value.length < 2) return
  const idx = selectedCompareVersions.value.indexOf(ver.id)
  if (idx > -1) {
    selectedCompareVersions.value.splice(idx, 1)
  } else {
    if (selectedCompareVersions.value.length >= 2) {
      selectedCompareVersions.value.shift()
    }
    selectedCompareVersions.value.push(ver.id)
  }
}

function clearCompareSelection() {
  selectedCompareVersions.value = []
}

function viewVersion(ver) {
  ElMessage.info(`查看版本 v${ver.version}（功能演示：可集成文档预览）`)
}

async function confirmRollback(ver) {
  try {
    const current = currentDoc.value
    await ElMessageBox.confirm(
      `将文档回退到 v${ver.version}，当前版本 v${current?.version} 的内容将不再用于问答，但版本历史中仍可查看。是否继续？`,
      '版本回退确认',
      {
        type: 'warning',
        confirmButtonText: '确认回退',
        cancelButtonText: '取消',
        dangerouslyUseHTMLString: true
      }
    )
    rollbackLoading.value = true
    const res = await rollbackToVersion(docId.value, ver.id)
    ElMessage.success(`回退任务已创建，正在处理...`)
    if (res.task_id) {
      pollRollbackStatus(res.task_id, res.document_id)
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('回退失败')
    }
  } finally {
    rollbackLoading.value = false
  }
}

function pollRollbackStatus(taskId, newDocId) {
  const poll = async () => {
    try {
      const task = await getTaskStatus(taskId)
      if (task.status === 'ready') {
        ElMessage.success('版本回退完成')
        await loadVersions()
        return
      }
      if (task.status === 'error') {
        ElMessage.error('版本回退处理失败')
        return
      }
      setTimeout(poll, 1500)
    } catch (e) {
      setTimeout(poll, 2000)
    }
  }
  poll()
}

async function startCompare() {
  if (selectedCompareVersions.value.length !== 2) {
    ElMessage.warning('请选择两个版本进行对比')
    return
  }

  const [id1, id2] = selectedCompareVersions.value
  const v1 = versions.value.find(v => v.id === id1)
  const v2 = versions.value.find(v => v.id === id2)

  let oldVer, newVer
  if (v1.version < v2.version) {
    oldVer = v1
    newVer = v2
  } else {
    oldVer = v2
    newVer = v1
  }

  compareOldVersion.value = oldVer.version
  compareNewVersion.value = newVer.version
  compareLoading.value = true

  try {
    compareResult.value = await compareVersions(oldVer.id, newVer.id)
    activeTab.value = 'compare'
  } catch (e) {
    ElMessage.error('对比失败')
  } finally {
    compareLoading.value = false
  }
}

async function exportDiffPdf() {
  if (selectedCompareVersions.value.length !== 2) {
    ElMessage.warning('请选择两个版本')
    return
  }
  try {
    const [id1, id2] = selectedCompareVersions.value
    const v1 = versions.value.find(v => v.id === id1)
    const v2 = versions.value.find(v => v.id === id2)
    let oldId, newId
    if (v1.version < v2.version) {
      oldId = v1.id
      newId = v2.id
    } else {
      oldId = v2.id
      newId = v1.id
    }
    const blob = await exportVersionDiffPdf(oldId, newId)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.download = `版本差异报告_v${compareOldVersion.value}_vs_v${compareNewVersion.value}.pdf`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('PDF导出成功')
  } catch (e) {
    ElMessage.error('PDF导出失败')
  }
}

function closeCompare() {
  compareResult.value = null
  activeTab.value = 'versions'
}

function getTimelineItemType(event) {
  if (event.event_type === 'rollback') return 'warning'
  return 'primary'
}

function getTimelineItemColor(event) {
  if (event.event_type === 'rollback') return '#e6a23c'
  if (event.change_type === 'major') return '#f56c6c'
  if (event.change_type === 'minor') return '#e6a23c'
  return '#67c23a'
}

function getChangeTypeTag(type) {
  const map = { major: 'danger', minor: 'warning', format: 'success' }
  return map[type] || 'info'
}

function getChangeTypeLabel(type) {
  const map = { major: '大幅修改', minor: '小幅修改', format: '格式调整' }
  return map[type] || '未知'
}

function canViewDiff(event) {
  return event.event_type !== 'rollback' && event.version > 1
}

function viewEventDiff(event) {
  const currentVer = versions.value.find(v => v.id === event.document_id)
  if (!currentVer) return
  const prevVer = versions.value.find(v => v.version === event.version - 1)
  if (!prevVer) {
    ElMessage.warning('不存在上一版本')
    return
  }
  selectedCompareVersions.value = [prevVer.id, currentVer.id]
  compareOldVersion.value = prevVer.version
  compareNewVersion.value = currentVer.version
  compareResult.value = null
  startCompare()
}

onMounted(() => {
  loadVersions()
  loadTimeline()
})
</script>

<style scoped>
.doc-versions-container {
  height: 100%;
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

.doc-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-right: 8px;
}

.main-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}

.main-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow: hidden;
}

.versions-panel, .compare-panel, .timeline-panel {
  height: 100%;
  padding: 20px;
  overflow: auto;
}

.compare-bar {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.compare-alert {
  flex: 1;
}

.compare-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.versions-list {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.version-item {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.version-item:hover {
  background: #fafbfc;
}

.version-item.is-active {
  background: #f0f9eb;
}

.version-item.is-selected {
  background: #ecf5ff;
}

.version-item:last-child {
  border-bottom: none;
}

.version-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.version-icon-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 40px;
  flex-shrink: 0;
}

.version-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 18px;
}

.version-icon.active {
  background: #67c23a;
  color: #fff;
}

.version-line {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: #e4e7ed;
  margin-top: 4px;
}

.version-info {
  flex: 1;
  min-width: 0;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.version-label {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.version-meta {
  font-size: 12px;
  color: #909399;
}

.dot {
  margin: 0 6px;
}

.version-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 16px;
}

.compare-doc-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.vs-icon {
  font-size: 18px;
  color: #909399;
}

.compare-actions {
  display: flex;
  gap: 8px;
}

.compare-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.summary-card {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 6px;
}

.summary-value.danger { color: #f56c6c; }
.summary-value.success { color: #67c23a; }
.summary-value.warning { color: #e6a23c; }
.summary-value.info { color: #909399; }

.summary-label {
  font-size: 13px;
  color: #606266;
}

.compare-content {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  height: calc(100% - 160px);
}

.diff-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.diff-chunk {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 3px solid;
}

.diff-chunk.deleted {
  background: #fef0f0;
  border-left-color: #f56c6c;
}

.diff-chunk.added {
  background: #f0f9eb;
  border-left-color: #67c23a;
}

.chunk-header {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.chunk-content {
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
}

.diff-pair {
  background: #fafbfc;
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.pair-header {
  padding: 10px 16px;
  background: #f5f7fa;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  border-bottom: 1px solid #ebeef5;
}

.pair-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: #ebeef5;
}

.pair-col {
  background: #fff;
  padding: 12px 16px;
}

.pair-col.old .col-title {
  color: #f56c6c;
}

.pair-col.new .col-title {
  color: #67c23a;
}

.col-title {
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 8px;
}

.col-body {
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.diff-html :deep(.diff-del) {
  background: #fde2e2;
  color: #f56c6c;
  text-decoration: line-through;
}

.diff-html :deep(.diff-add) {
  background: #e1f3d8;
  color: #67c23a;
  text-decoration: underline;
}

.timeline-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 16px;
}

.timeline-list {
  padding: 0 12px;
}

.timeline-card {
  background: #fff;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.timeline-card.is-rollback {
  border-left: 4px solid #e6a23c;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.event-version {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.timeline-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.summary-item.add { color: #67c23a; font-weight: 500; }
.summary-item.del { color: #f56c6c; font-weight: 500; }
.summary-item.mod { color: #e6a23c; font-weight: 500; }
.summary-item.total { color: #909399; }

.timeline-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.timeline-actions {
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
</style>
