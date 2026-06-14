<template>
  <div class="debug-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回知识库
        </el-button>
        <el-divider direction="vertical" />
        <span class="page-title">
          <el-icon><Setting /></el-icon> 检索调试面板
        </span>
        <el-tag size="small" type="warning">Developer</el-tag>
      </div>
      <el-tag size="small" type="info" v-if="kb">
        知识库: {{ kb.name }}
      </el-tag>
    </div>

    <div class="debug-content">
      <div class="query-panel">
        <el-input
          v-model="query"
          type="textarea"
          :rows="2"
          placeholder="输入查询语句进行检索调试"
          @keydown.enter.ctrl="doSearch"
        />
        <div class="query-options">
          <el-form :inline="true" size="small">
            <el-form-item label="Top-K">
              <el-input-number v-model="topK" :min="5" :max="100" />
            </el-form-item>
            <el-form-item label="重排序">
              <el-switch v-model="enableRerank" />
            </el-form-item>
          </el-form>
        </div>
        <el-button type="primary" :icon="Search" :loading="searching" @click="doSearch">
          执行检索 (Ctrl+Enter)
        </el-button>
      </div>

      <div v-if="debugInfo || results.length > 0" class="results-panel">
        <div class="timeline">
          <el-divider content-position="left">
            <h3>检索流程</h3>
          </el-divider>

          <el-steps :active="4" finish-status="success" align-center>
            <el-step title="向量化" :description="embeddingDesc" />
            <el-step title="Top-K召回" :description="recallDesc" />
            <el-step title="重排序" :description="rerankDesc" />
            <el-step title="MMR过滤" :description="mmrDesc" />
          </el-steps>
        </div>

        <div class="stages">
          <el-collapse v-model="activeStages">
            <el-collapse-item name="recall">
              <template #title>
                <span class="stage-title">
                  <el-tag size="small" type="info">Step 1</el-tag>
                  Top-K 初始召回
                  <el-tag size="small">{{ debugInfo?.initial_recall?.length || 0 }} 条</el-tag>
                </span>
              </template>
              <el-table :data="debugInfo?.initial_recall || []" size="small" border>
                <el-table-column label="#" width="50">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column prop="document_name" label="文档" min-width="150" />
                <el-table-column prop="score" label="初始得分" width="100">
                  <template #default="{ row }">{{ row.score?.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column prop="content_summary" label="内容摘要" min-width="300" />
              </el-table>
            </el-collapse-item>

            <el-collapse-item name="rerank">
              <template #title>
                <span class="stage-title">
                  <el-tag size="small" type="warning">Step 2</el-tag>
                  Cross-Encoder 重排序 (Top 5)
                </span>
              </template>
              <el-table :data="debugInfo?.reranked_top_n || []" size="small" border>
                <el-table-column prop="rank" label="排名" width="60" />
                <el-table-column prop="document_name" label="文档" min-width="150" />
                <el-table-column label="综合得分" width="100">
                  <template #default="{ row }">
                    <el-tag type="primary" size="small">{{ row.combined_score?.toFixed(4) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="initial_score" label="初始得分" width="90">
                  <template #default="{ row }">{{ row.initial_score?.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column prop="rerank_score" label="重排得分" width="90">
                  <template #default="{ row }">{{ row.rerank_score?.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column prop="content_summary" label="内容摘要" min-width="250" />
              </el-table>
            </el-collapse-item>

            <el-collapse-item name="mmr">
              <template #title>
                <span class="stage-title">
                  <el-tag size="small" type="success">Step 3</el-tag>
                  MMR 多样性过滤 (最终结果)
                  <el-tag size="small" type="success">{{ debugInfo?.mmr_filtered?.length || 0 }} 条</el-tag>
                </span>
              </template>
              <div class="final-results">
                <div v-for="(item, idx) in debugInfo?.mmr_filtered || results" :key="item.chunk_id" class="result-card">
                  <div class="result-header">
                    <el-tag type="success" size="small">#{{ idx + 1 }}</el-tag>
                    <span class="doc-name">{{ item.document_name }}</span>
                    <el-tag size="small">得分: {{ item.score?.toFixed(4) || item.final_score?.toFixed(4) }}</el-tag>
                  </div>
                  <div class="result-content">{{ item.content || item.content_summary }}</div>
                </div>
                <el-empty v-if="results.length === 0" description="无结果" />
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>

      <div v-else class="empty-state">
        <el-icon class="empty-icon"><Search /></el-icon>
        <p>输入查询后查看检索全流程</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Setting, Search
} from '@element-plus/icons-vue'
import { getKnowledgeBase, searchDocuments } from '@/api'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.kbId)

const kb = ref(null)
const query = ref('')
const topK = ref(20)
const enableRerank = ref(true)
const searching = ref(false)
const results = ref([])
const debugInfo = ref(null)
const activeStages = ref(['recall', 'rerank', 'mmr'])

const embeddingDesc = computed(() => {
  if (!debugInfo.value) return ''
  return `${debugInfo.value.embedding_time_ms || 0} ms`
})

const recallDesc = computed(() => {
  if (!debugInfo.value) return ''
  return `${debugInfo.value.search_time_ms || 0} ms · ${debugInfo.value.initial_recall_count || 0}条`
})

const rerankDesc = computed(() => {
  if (!debugInfo.value) return ''
  if (!enableRerank.value) return '已禁用'
  return `${debugInfo.value.rerank_time_ms || 0} ms`
})

const mmrDesc = computed(() => {
  if (!debugInfo.value) return ''
  return `${debugInfo.value.mmr_time_ms || 0} ms · ${debugInfo.value.final_count || 0}条`
})

function goBack() {
  router.push(`/knowledge-bases/${kbId.value}`)
}

async function loadKb() {
  kb.value = await getKnowledgeBase(kbId.value)
  if (kb.value) {
    topK.value = kb.value.top_k || 20
    enableRerank.value = kb.value.enable_rerank ?? true
  }
}

async function doSearch() {
  if (!query.value.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }
  searching.value = true
  try {
    const resp = await searchDocuments({
      query: query.value,
      knowledge_base_id: kbId.value,
      top_k: topK.value,
      enable_rerank: enableRerank.value
    })
    results.value = resp.results || []
    debugInfo.value = resp.debug_info || null
  } catch (e) {
  } finally {
    searching.value = false
  }
}

onMounted(loadKb)
</script>

<style scoped>
.debug-container {
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
  padding: 0 24px;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.debug-content {
  flex: 1;
  padding: 24px;
  overflow: auto;
}

.query-panel {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.query-options {
  margin: 12px 0;
}

.results-panel {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
}

.stage-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.timeline {
  margin-bottom: 20px;
}

.stages {
  margin-top: 20px 0;
}

.final-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px;
  background: #fafbfc;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  flex: 1;
}

.result-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  background: #fff;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #909399;
}

.empty-icon {
  font-size: 64px;
  color: #409eff;
  margin-bottom: 16px;
}
</style>
