<template>
  <div class="compare-result-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="page-title">文档对比分析</span>
      </div>
      <div class="nav-right">
        <el-tooltip content="显示已忽略项" placement="bottom">
          <el-switch
            v-model="showIgnored"
            @change="toggleShowIgnored"
            style="margin-right: 12px;"
          />
        </el-tooltip>
        <el-button
          type="primary"
          size="small"
          :loading="exporting"
          :icon="Download"
          :disabled="result?.status !== 'completed'"
          @click="handleExportPdf"
        >
          {{ exporting ? '生成中...' : '导出PDF' }}
        </el-button>
        <el-tag v-if="result?.status === 'completed'" type="success" size="small">对比完成</el-tag>
        <el-tag v-else-if="result?.status === 'error'" type="danger" size="small">对比失败</el-tag>
        <el-tag v-else type="warning" size="small">正在处理...</el-tag>
      </div>
    </div>

    <div class="compare-content" v-loading="loading">
      <template v-if="result && result.status === 'completed'">
        <div class="doc-info-bar">
          <div class="doc-info-item doc-a">
            <el-icon><Document /></el-icon>
            <span class="doc-name">{{ result.doc_a?.filename }}</span>
            <el-tag size="small" type="info">{{ result.doc_a?.chunk_count }} 个分块</el-tag>
          </div>
          <div class="vs-badge">VS</div>
          <div class="doc-info-item doc-b">
            <el-icon><Document /></el-icon>
            <span class="doc-name">{{ result.doc_b?.filename }}</span>
            <el-tag size="small" type="info">{{ result.doc_b?.chunk_count }} 个分块</el-tag>
          </div>
        </div>

        <div class="summary-cards">
          <div class="summary-card unique-a">
            <div class="summary-value">{{ result.summary?.unique_a_count }}</div>
            <div class="summary-label">文档 A 独有内容</div>
          </div>
          <div class="summary-card unique-b">
            <div class="summary-value">{{ result.summary?.unique_b_count }}</div>
            <div class="summary-label">文档 B 独有内容</div>
          </div>
          <div class="summary-card similar">
            <div class="summary-value">{{ result.summary?.similar_count }}</div>
            <div class="summary-label">相似但有差异</div>
          </div>
          <div class="summary-card repeated">
            <div class="summary-value">{{ result.summary?.repeated_count }}</div>
            <div class="summary-label">高度重复</div>
          </div>
        </div>

        <el-tabs v-model="activeTab" class="compare-tabs">
          <el-tab-pane label="独有内容" name="unique">
            <div class="unique-content">
              <div class="unique-column">
                <div class="column-header">
                  <span>文档 A 独有 ({{ result.unique_a?.length || 0 }})</span>
                </div>
                <el-scrollbar class="chunk-list">
                  <el-empty v-if="!result.unique_a || result.unique_a.length === 0" description="无独有内容" :image-size="60" />
                  <div v-for="chunk in result.unique_a" :key="chunk.chunk_id" class="chunk-card">
                    <div class="chunk-meta">
                      <el-tag size="small" type="warning">第 {{ chunk.chunk_index + 1 }} 块</el-tag>
                      <span v-if="chunk.page_number" class="page-info">第 {{ chunk.page_number }} 页</span>
                    </div>
                    <div class="chunk-content">{{ getContentPreview(chunk.content) }}</div>
                  </div>
                </el-scrollbar>
              </div>
              <div class="unique-column">
                <div class="column-header">
                  <span>文档 B 独有 ({{ result.unique_b?.length || 0 }})</span>
                </div>
                <el-scrollbar class="chunk-list">
                  <el-empty v-if="!result.unique_b || result.unique_b.length === 0" description="无独有内容" :image-size="60" />
                  <div v-for="chunk in result.unique_b" :key="chunk.chunk_id" class="chunk-card">
                    <div class="chunk-meta">
                      <el-tag size="small" type="warning">第 {{ chunk.chunk_index + 1 }} 块</el-tag>
                      <span v-if="chunk.page_number" class="page-info">第 {{ chunk.page_number }} 页</span>
                    </div>
                    <div class="chunk-content">{{ getContentPreview(chunk.content) }}</div>
                  </div>
                </el-scrollbar>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="重复内容" name="repeated">
            <div class="repeated-content">
              <el-empty v-if="!result.repeated_pairs || result.repeated_pairs.length === 0" description="无高度重复内容" :image-size="80" />
              <el-table v-else :data="result.repeated_pairs" stripe>
                <el-table-column label="文档 A" min-width="260">
                  <template #default="{ row }">
                    <div class="repeated-cell">
                      <div class="cell-meta">
                        <el-tag size="small" type="primary">第 {{ row.chunk_a.chunk_index + 1 }} 块</el-tag>
                        <span v-if="row.chunk_a.page_number" class="page-info">第 {{ row.chunk_a.page_number }} 页</span>
                      </div>
                      <div class="cell-content">{{ getContentPreview(row.chunk_a.content) }}</div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="相似度" width="100" align="center">
                  <template #default="{ row }">
                    <el-tag type="success" size="small">{{ formatSimilarity(row.similarity) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="文档 B" min-width="260">
                  <template #default="{ row }">
                    <div class="repeated-cell">
                      <div class="cell-meta">
                        <el-tag size="small" type="success">第 {{ row.chunk_b.chunk_index + 1 }} 块</el-tag>
                        <span v-if="row.chunk_b.page_number" class="page-info">第 {{ row.chunk_b.page_number }} 页</span>
                      </div>
                      <div class="cell-content">{{ getContentPreview(row.chunk_b.content) }}</div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="80" align="center" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-if="!isPairIgnored(row.chunk_a.chunk_id, row.chunk_b.chunk_id)"
                      text
                      type="warning"
                      size="small"
                      @click="handleIgnorePair(row.chunk_a.chunk_id, row.chunk_b.chunk_id, 'repeated')"
                    >
                      忽略
                    </el-button>
                    <el-button
                      v-else
                      text
                      type="primary"
                      size="small"
                      @click="handleUnignorePair(row.chunk_a.chunk_id, row.chunk_b.chunk_id)"
                    >
                      取消忽略
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>

          <el-tab-pane label="差异内容" name="similar">
            <div class="similar-content">
              <el-empty v-if="!result.similar_pairs || result.similar_pairs.length === 0" description="无相似但有差异的内容" :image-size="80" />
              <div v-else class="diff-list">
                <div v-for="(pair, idx) in result.similar_pairs" :key="`${pair.chunk_a.chunk_id}-${pair.chunk_b.chunk_id}`" class="diff-item">
                  <div class="diff-header">
                    <div class="diff-title">差异对 #{{ idx + 1 }}</div>
                    <div class="diff-header-actions">
                      <el-tag size="small" type="warning" style="margin-right: 8px;">相似度 {{ formatSimilarity(pair.similarity) }}</el-tag>
                      <el-button
                        v-if="!isPairIgnored(pair.chunk_a.chunk_id, pair.chunk_b.chunk_id)"
                        text
                        type="warning"
                        size="small"
                        @click="handleIgnorePair(pair.chunk_a.chunk_id, pair.chunk_b.chunk_id, 'similar')"
                      >
                        忽略
                      </el-button>
                      <el-button
                        v-else
                        text
                        type="primary"
                        size="small"
                        @click="handleUnignorePair(pair.chunk_a.chunk_id, pair.chunk_b.chunk_id)"
                      >
                        取消忽略
                      </el-button>
                    </div>
                  </div>
                  <div class="diff-columns">
                    <div class="diff-col">
                      <div class="diff-col-header">
                        <span class="col-label">文档 A</span>
                        <span class="col-meta">第 {{ pair.chunk_a.chunk_index + 1 }} 块</span>
                        <span v-if="pair.chunk_a.page_number" class="col-meta">第 {{ pair.chunk_a.page_number }} 页</span>
                      </div>
                      <div class="diff-text" v-html="getDiffHtml(pair.diff_a)"></div>
                    </div>
                    <div class="diff-col">
                      <div class="diff-col-header">
                        <span class="col-label">文档 B</span>
                        <span class="col-meta">第 {{ pair.chunk_b.chunk_index + 1 }} 块</span>
                        <span v-if="pair.chunk_b.page_number" class="col-meta">第 {{ pair.chunk_b.page_number }} 页</span>
                      </div>
                      <div class="diff-text" v-html="getDiffHtml(pair.diff_b)"></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>

      <template v-else-if="result && result.status === 'error'">
        <div class="error-box">
          <el-icon class="error-icon"><CircleClose /></el-icon>
          <h3>对比分析失败</h3>
          <p>{{ result.error_message || '未知错误' }}</p>
        </div>
      </template>

      <template v-else>
        <div class="loading-box">
          <el-icon class="loading-icon"><Loading /></el-icon>
          <h3>正在进行对比分析...</h3>
          <p>{{ result?.message || '请稍候' }}</p>
          <el-progress :percentage="result?.progress || 0" :stroke-width="6" style="width: 300px; margin-top: 16px;" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Document, CircleClose, Loading, Download
} from '@element-plus/icons-vue'
import {
  getCompareResult, addIgnorePair, removeIgnorePair, exportComparePdf
} from '@/api'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.id)
const taskId = computed(() => route.params.taskId)

const loading = ref(false)
const exporting = ref(false)
const result = ref(null)
const activeTab = ref('unique')
const showIgnored = ref(false)
const ignoredPairsMap = ref(new Map())
const serverFiltered = ref(true)
let pollTimer = null

function goBack() {
  router.push(`/knowledge-bases/${kbId.value}`)
}

function getContentPreview(content) {
  if (!content) return ''
  return content.length > 200 ? content.substring(0, 200) + '...' : content
}

function formatSimilarity(score) {
  if (score == null) return '0%'
  return (score * 100).toFixed(1) + '%'
}

function getDiffHtml(html) {
  if (!html || typeof html !== 'string') {
    return ''
  }
  return html
}

function getPairKey(chunkAId, chunkBId) {
  return [chunkAId, chunkBId].sort().join('|')
}

function isPairIgnored(chunkAId, chunkBId) {
  return ignoredPairsMap.value.has(getPairKey(chunkAId, chunkBId))
}

async function loadResult() {
  try {
    const data = await getCompareResult(taskId.value, showIgnored.value)

    const map = new Map()
    if (data.ignored_pairs && data.ignored_pairs.length) {
      data.ignored_pairs.forEach(p => {
        map.set(getPairKey(p.chunk_a_id, p.chunk_b_id), p)
      })
    }
    ignoredPairsMap.value = map

    if (!showIgnored.value && map.size > 0) {
      if (data.repeated_pairs) {
        data.repeated_pairs = data.repeated_pairs.filter(
          p => !map.has(getPairKey(p.chunk_a?.chunk_id, p.chunk_b?.chunk_id))
        )
      }
      if (data.similar_pairs) {
        data.similar_pairs = data.similar_pairs.filter(
          p => !map.has(getPairKey(p.chunk_a?.chunk_id, p.chunk_b?.chunk_id))
        )
      }
      if (data.summary) {
        data.summary.repeated_count = data.repeated_pairs?.length || 0
        data.summary.similar_count = data.similar_pairs?.length || 0
      }
    }

    result.value = data

    if (data.status === 'completed' || data.status === 'error') {
      stopPolling()
    }
  } catch (e) {
    ElMessage.error('加载对比结果失败')
    stopPolling()
  }
}

async function toggleShowIgnored(val) {
  showIgnored.value = val
  await loadResult()
}

async function handleIgnorePair(chunkAId, chunkBId, ignoreType) {
  try {
    await addIgnorePair({
      task_id: taskId.value,
      chunk_a_id: chunkAId,
      chunk_b_id: chunkBId,
      ignore_type: ignoreType
    })
    ignoredPairsMap.value.set(getPairKey(chunkAId, chunkBId), { chunk_a_id: chunkAId, chunk_b_id: chunkBId })
    ElMessage.success('已忽略该条目')
    await loadResult()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function handleUnignorePair(chunkAId, chunkBId) {
  try {
    await removeIgnorePair(taskId.value, chunkAId, chunkBId)
    ignoredPairsMap.value.delete(getPairKey(chunkAId, chunkBId))
    ElMessage.success('已取消忽略')
    await loadResult()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function handleExportPdf() {
  if (exporting.value) return
  exporting.value = true
  try {
    const blob = await exportComparePdf(taskId.value)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    const docA = result.value?.doc_a?.filename || 'docA'
    const docB = result.value?.doc_b?.filename || 'docB'
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    link.setAttribute('download', `对比报告_${docA.slice(0, 15)}_vs_${docB.slice(0, 15)}_${ts}.pdf`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('PDF导出成功')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || 'PDF导出失败')
  } finally {
    exporting.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(() => {
    loadResult()
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadResult()
    if (result.value && result.value.status !== 'completed' && result.value.status !== 'error') {
      startPolling()
    }
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.compare-result-container {
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

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.compare-content {
  flex: 1;
  padding: 20px;
  overflow: auto;
}

.loading-box, .error-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #909399;
}

.loading-icon, .error-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.loading-icon {
  color: #409eff;
  animation: spin 1s linear infinite;
}

.error-icon {
  color: #f56c6c;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-box h3, .error-box h3 {
  font-size: 18px;
  color: #303133;
  margin-bottom: 8px;
}

.doc-info-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.doc-info-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  background: #f5f7fa;
}

.doc-info-item.doc-a {
  border-left: 3px solid #409eff;
}

.doc-info-item.doc-b {
  border-left: 3px solid #67c23a;
}

.doc-info-item .el-icon {
  font-size: 20px;
  color: #606266;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vs-badge {
  font-size: 14px;
  font-weight: 700;
  color: #909399;
  background: #f0f2f5;
  padding: 4px 12px;
  border-radius: 12px;
}

.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  border-top: 3px solid #dcdfe6;
}

.summary-card.unique-a {
  border-top-color: #409eff;
}

.summary-card.unique-b {
  border-top-color: #67c23a;
}

.summary-card.similar {
  border-top-color: #e6a23c;
}

.summary-card.repeated {
  border-top-color: #909399;
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 8px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
}

.compare-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 0 20px;
}

.compare-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.unique-content {
  display: flex;
  gap: 16px;
  min-height: 400px;
}

.unique-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fafafa;
  border-radius: 6px;
  overflow: hidden;
}

.column-header {
  padding: 12px 16px;
  background: #f0f2f5;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  flex-shrink: 0;
}

.chunk-list {
  flex: 1;
  max-height: 500px;
  padding: 12px;
}

.chunk-card {
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid #ebeef5;
  transition: all 0.2s;
}

.chunk-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.chunk-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.page-info {
  font-size: 12px;
  color: #909399;
}

.chunk-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.repeated-content {
  min-height: 400px;
}

.repeated-cell {
  padding: 4px 0;
}

.cell-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.cell-content {
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.similar-content {
  min-height: 400px;
}

.diff-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.diff-item {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}

.diff-header-actions {
  display: flex;
  align-items: center;
}

.diff-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.diff-columns {
  display: flex;
  gap: 1px;
  background: #ebeef5;
}

.diff-col {
  flex: 1;
  background: #fff;
}

.diff-col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
  font-size: 12px;
}

.col-label {
  font-weight: 600;
  color: #303133;
}

.col-meta {
  color: #909399;
  font-size: 11px;
}

.diff-text {
  padding: 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.diff-text :deep(.diff-equal) {
  color: #909399;
}

.diff-text :deep(.diff-add) {
  background: #f0f9eb;
  color: #67c23a;
  padding: 1px 2px;
  border-radius: 2px;
}

.diff-text :deep(.diff-del) {
  background: #fef0f0;
  color: #f56c6c;
  padding: 1px 2px;
  border-radius: 2px;
  text-decoration: line-through;
}
</style>
