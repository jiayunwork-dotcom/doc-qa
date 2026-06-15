<template>
  <div class="batch-overview-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="page-title">批量对比总览</span>
        <el-tag v-if="overview?.status === 'completed'" type="success" size="small">对比完成</el-tag>
        <el-tag v-else-if="overview?.status === 'error'" type="danger" size="small">对比失败</el-tag>
        <el-tag v-else type="warning" size="small">处理中 {{ overview?.progress || 0 }}%</el-tag>
      </div>
      <div class="nav-right">
        <span class="doc-count">共 {{ overview?.document_ids?.length || 0 }} 篇文档</span>
      </div>
    </div>

    <div class="overview-content" v-loading="loading">
      <template v-if="overview && (overview.status === 'completed' || overview.status === 'processing' || overview.status === 'pending')">
        <div class="progress-bar-wrapper" v-if="overview.status !== 'completed'">
          <div class="progress-info">
            <span>{{ overview.message || '正在批量对比...' }}</span>
            <span class="progress-text">{{ overview.completed_pairs || 0 }} / {{ overview.total_pairs || 0 }} 对完成</span>
          </div>
          <el-progress :percentage="overview.progress || 0" :stroke-width="8" />
        </div>

        <div class="legend-bar">
          <span class="legend-title">重复率图例：</span>
          <div class="legend-gradient"></div>
          <span class="legend-value">0%</span>
          <span class="legend-value">50%</span>
          <span class="legend-value">100%</span>
        </div>

        <div class="matrix-wrapper">
          <el-scrollbar>
            <table class="heatmap-table">
              <thead>
                <tr>
                  <th class="corner-cell"></th>
                  <th v-for="(name, idx) in overview.document_names" :key="'h-'+idx" class="header-cell" :title="name">
                    <div class="header-text" :style="{ transform: 'rotate(-45deg)', transformOrigin: 'left bottom', whiteSpace: 'nowrap' }">
                      {{ truncateName(name) }}
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in overview.matrix" :key="'r-'+i">
                  <td class="row-header-cell" :title="overview.document_names[i]">
                    {{ truncateName(overview.document_names[i]) }}
                  </td>
                  <td
                    v-for="(cell, j) in row"
                    :key="'c-'+i+'-'+j"
                    class="matrix-cell"
                    :class="getCellClass(cell, i, j)"
                    :style="getCellStyle(cell, i, j)"
                    @click="handleCellClick(cell, i, j)"
                  >
                    <el-tooltip
                      v-if="i !== j"
                      :content="getTooltipContent(cell)"
                      placement="top"
                    >
                      <span class="cell-value" :class="{ 'clickable': cell.status === 'completed' }">
                        {{ cell.status === 'completed' ? formatRepeatRate(cell.repeat_rate) : getStatusLabel(cell.status) }}
                      </span>
                    </el-tooltip>
                    <span v-else class="cell-value self-cell">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </el-scrollbar>
        </div>

        <div class="legend-bar" style="margin-top: 16px;">
          <span class="legend-title">状态说明：</span>
          <el-tag size="small" type="success">已完成</el-tag>
          <el-tag size="small" type="warning">处理中</el-tag>
          <el-tag size="small" type="danger">失败</el-tag>
          <el-tag size="small" type="info">自身对比</el-tag>
          <span style="color: #909399; font-size: 12px; margin-left: 12px;">点击已完成的单元格可跳转到该对文档的详细对比结果</span>
        </div>
      </template>

      <template v-else-if="overview && overview.status === 'error'">
        <div class="error-box">
          <el-icon class="error-icon"><CircleClose /></el-icon>
          <h3>批量对比失败</h3>
          <p>{{ overview.error_message || '未知错误' }}</p>
          <el-button type="primary" @click="goBack" style="margin-top: 16px;">返回</el-button>
        </div>
      </template>

      <template v-else>
        <div class="loading-box">
          <el-icon class="loading-icon"><Loading /></el-icon>
          <h3>加载批量对比数据...</h3>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, CircleClose, Loading } from '@element-plus/icons-vue'
import { getBatchCompareOverview, getBatchCompareStatus } from '@/api'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.id)
const batchTaskId = computed(() => route.params.batchTaskId)

const loading = ref(false)
const overview = ref(null)
let pollTimer = null

function goBack() {
  router.push(`/knowledge-bases/${kbId.value}`)
}

function truncateName(name) {
  if (!name) return ''
  return name.length > 20 ? name.slice(0, 18) + '...' : name
}

function getCellClass(cell, i, j) {
  if (i === j) return 'self'
  if (cell.status === 'completed') return 'completed'
  if (cell.status === 'processing' || cell.status === 'loading') return 'processing'
  if (cell.status === 'error') return 'error'
  return 'pending'
}

function getCellStyle(cell, i, j) {
  if (i === j) {
    return { background: '#f5f7fa' }
  }
  if (cell.status !== 'completed') {
    return { background: '#fafafa' }
  }
  const rate = Math.min(Math.max(cell.repeat_rate, 0), 100)
  const r = Math.max(Math.round(255 - rate * 1.5), 0)
  const g = Math.max(Math.round(255 - rate * 1.2), 0)
  const b = Math.max(Math.round(255 - rate * 0.5), 0)
  return {
    background: `rgb(${r}, ${g}, ${b})`,
    color: rate > 60 ? '#fff' : '#303133'
  }
}

function formatRepeatRate(rate) {
  if (rate == null) return '0.0%'
  const safeRate = Math.min(Math.max(parseFloat(rate) || 0, 0), 100)
  return safeRate.toFixed(1) + '%'
}

function getTooltipContent(cell) {
  if (cell.status === 'completed') {
    const rate = Math.min(Math.max(cell.repeat_rate, 0), 100)
    return `${cell.doc_a_name} vs ${cell.doc_b_name}\n重复率: ${rate.toFixed(1)}%\n重复块数: ${cell.repeated_count}/${cell.min_chunk_count}`
  }
  if (cell.status === 'processing' || cell.status === 'loading' || cell.status === 'pending') {
    return `正在对比中: ${cell.doc_a_name} vs ${cell.doc_b_name}`
  }
  if (cell.status === 'error') {
    return `对比失败: ${cell.doc_a_name} vs ${cell.doc_b_name}`
  }
  return `${cell.doc_a_name} vs ${cell.doc_b_name}`
}

function getStatusLabel(status) {
  const map = {
    pending: '等待',
    processing: '处理中',
    loading: '处理中',
    error: '失败'
  }
  return map[status] || '...'
}

function handleCellClick(cell, i, j) {
  if (i === j) return
  if (cell.status === 'completed' && cell.task_id) {
    router.push(`/knowledge-bases/${kbId.value}/compare/${cell.task_id}`)
  } else if (cell.status === 'error') {
    ElMessage.warning('该对文档对比失败，无法查看详情')
  } else {
    ElMessage.info('该对文档仍在对比中，请稍候')
  }
}

async function loadOverview() {
  try {
    const data = await getBatchCompareOverview(batchTaskId.value)
    overview.value = data

    if (data.status === 'completed' || data.status === 'error') {
      stopPolling()
    }
  } catch (e) {
    try {
      const status = await getBatchCompareStatus(batchTaskId.value)
      overview.value = {
        ...status,
        document_ids: [],
        document_names: [],
        matrix: [],
        error_message: ''
      }
    } catch (e2) {
      ElMessage.error('加载批量对比数据失败')
      stopPolling()
    }
  }
}

function startPolling() {
  pollTimer = setInterval(() => {
    loadOverview()
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
    await loadOverview()
    if (overview.value && overview.value.status !== 'completed' && overview.value.status !== 'error') {
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
.batch-overview-container {
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

.doc-count {
  font-size: 13px;
  color: #606266;
}

.overview-content {
  flex: 1;
  padding: 20px;
  overflow: auto;
  background: #f5f7fa;
}

.progress-bar-wrapper {
  background: #fff;
  padding: 16px 20px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  color: #606266;
}

.progress-text {
  color: #909399;
}

.legend-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  padding: 12px 20px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
}

.legend-title {
  color: #606266;
  font-weight: 500;
}

.legend-gradient {
  width: 200px;
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(to right, rgb(255, 255, 255), rgb(180, 210, 120), rgb(105, 75, 175));
}

.legend-value {
  font-size: 11px;
  color: #909399;
  min-width: 36px;
}

.matrix-wrapper {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  overflow: auto;
  max-height: calc(100vh - 260px);
}

.heatmap-table {
  border-collapse: collapse;
  margin: 0 auto;
}

.heatmap-table th,
.heatmap-table td {
  border: 1px solid #ebeef5;
  padding: 0;
}

.corner-cell {
  width: 140px;
  height: 120px;
  background: #fafafa;
  border: none !important;
  border-bottom: 1px solid #ebeef5 !important;
  border-right: 1px solid #ebeef5 !important;
}

.header-cell {
  width: 48px;
  height: 120px;
  background: #fafafa;
  text-align: left;
  vertical-align: bottom;
  font-weight: 500;
  color: #303133;
  padding: 8px !important;
  white-space: nowrap;
  overflow: hidden;
}

.header-text {
  font-size: 12px;
  display: inline-block;
  padding: 4px 0;
  color: #303133;
  width: 100%;
}

.row-header-cell {
  width: 140px;
  height: 48px;
  background: #fafafa;
  font-weight: 500;
  color: #303133;
  padding: 8px 12px !important;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.matrix-cell {
  width: 48px;
  height: 48px;
  text-align: center;
  vertical-align: middle;
  cursor: default;
  transition: all 0.2s;
  font-size: 11px;
}

.matrix-cell.completed {
  cursor: pointer;
}

.matrix-cell.completed:hover {
  transform: scale(1.1);
  z-index: 10;
  position: relative;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  border: 2px solid #409eff !important;
}

.matrix-cell.self {
  cursor: default;
}

.cell-value {
  display: inline-block;
  font-weight: 600;
  font-size: 11px;
}

.cell-value.clickable {
  cursor: pointer;
}

.cell-value.self-cell {
  color: #c0c4cc;
  font-weight: 400;
}

.matrix-cell.processing {
  background: #fdf6ec !important;
}
.matrix-cell.processing .cell-value {
  color: #e6a23c;
}

.matrix-cell.error {
  background: #fef0f0 !important;
}
.matrix-cell.error .cell-value {
  color: #f56c6c;
}

.matrix-cell.pending {
  background: #f4f4f5 !important;
}
.matrix-cell.pending .cell-value {
  color: #909399;
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
</style>
