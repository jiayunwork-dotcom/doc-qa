<template>
  <div class="kb-list-container">
    <div class="kb-list-header">
      <div class="header-left">
        <el-icon class="logo-icon"><Reading /></el-icon>
        <h1 class="title">文档智能问答平台</h1>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        创建知识库
      </el-button>
    </div>

    <div v-loading="loading" class="kb-card-grid">
      <el-empty v-if="!loading && knowledgeBases.length === 0" description="暂无知识库，点击右上角创建">
        <el-button type="primary" @click="showCreateDialog = true">创建知识库</el-button>
      </el-empty>

      <el-card
        v-for="kb in knowledgeBases"
        :key="kb.id"
        class="kb-card"
        shadow="hover"
        @click="enterKnowledgeBase(kb.id)"
      >
        <div class="card-header">
          <div class="card-title">
            <el-icon><Folder /></el-icon>
            <span class="kb-name">{{ kb.name }}</span>
          </div>
          <el-dropdown trigger="click" @click.stop>
            <el-button text :icon="MoreFilled" size="small" @click.stop />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click.stop="editKnowledgeBase(kb)">
                  <el-icon><Edit /></el-icon> 编辑
                </el-dropdown-item>
                <el-dropdown-item divided @click.stop="confirmDelete(kb)">
                  <el-icon><Delete /></el-icon> 删除
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="card-desc">{{ kb.description || '暂无描述' }}</div>
        <div class="card-footer">
          <div class="card-meta">
            <el-tag size="small" type="info">
              <el-icon><Document /></el-icon> {{ kb.document_count }} 篇文档
            </el-tag>
          </div>
          <div class="card-time">
            {{ formatTime(kb.updated_at) }}
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog
      v-model="showCreateDialog"
      :title="editingKb ? '编辑知识库' : '创建知识库'"
      width="520px"
      @closed="resetForm"
    >
      <el-form :model="formData" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入知识库名称" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="formData.description" type="textarea" :rows="3" placeholder="请输入知识库描述" />
        </el-form-item>
        <el-form-item label="分块策略">
          <el-select v-model="formData.chunk_strategy" style="width: 100%">
            <el-option label="固定长度分块" value="fixed" />
            <el-option label="语义分段" value="semantic" />
            <el-option label="按标题层级" value="heading" />
          </el-select>
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="formData.chunk_size" :min="100" :max="2000" :step="100" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">字符数</span>
        </el-form-item>
        <el-form-item label="重叠大小">
          <el-input-number v-model="formData.chunk_overlap" :min="0" :max="500" :step="50" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px;">字符数</span>
        </el-form-item>
        <el-form-item label="检索Top-K">
          <el-input-number v-model="formData.top_k" :min="5" :max="100" />
        </el-form-item>
        <el-form-item label="重排序">
          <el-switch v-model="formData.enable_rerank" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, MoreFilled, Folder, Edit, Delete, Document, Reading
} from '@element-plus/icons-vue'
import {
  listKnowledgeBases, createKnowledgeBase, updateKnowledgeBase, deleteKnowledgeBase
} from '@/api'

const router = useRouter()
const loading = ref(false)
const knowledgeBases = ref([])
const showCreateDialog = ref(false)
const formRef = ref(null)
const editingKb = ref(null)

const formData = reactive({
  name: '',
  description: '',
  chunk_strategy: 'fixed',
  chunk_size: 500,
  chunk_overlap: 100,
  top_k: 20,
  enable_rerank: true
})

const formRules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }]
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function fetchData() {
  loading.value = true
  try {
    knowledgeBases.value = await listKnowledgeBases()
  } finally {
    loading.value = false
  }
}

function enterKnowledgeBase(id) {
  router.push(`/knowledge-bases/${id}`)
}

function editKnowledgeBase(kb) {
  editingKb.value = kb
  Object.assign(formData, {
    name: kb.name,
    description: kb.description || '',
    chunk_strategy: kb.chunk_strategy,
    chunk_size: kb.chunk_size,
    chunk_overlap: kb.chunk_overlap,
    top_k: kb.top_k,
    enable_rerank: kb.enable_rerank
  })
  showCreateDialog.value = true
}

function resetForm() {
  editingKb.value = null
  Object.assign(formData, {
    name: '',
    description: '',
    chunk_strategy: 'fixed',
    chunk_size: 500,
    chunk_overlap: 100,
    top_k: 20,
    enable_rerank: true
  })
  formRef.value?.resetFields()
}

async function submitForm() {
  await formRef.value.validate()
  try {
    if (editingKb.value) {
      await updateKnowledgeBase(editingKb.value.id, formData)
      ElMessage.success('更新成功')
    } else {
      await createKnowledgeBase(formData)
      ElMessage.success('创建成功')
    }
    showCreateDialog.value = false
    fetchData()
  } catch (e) {}
}

async function confirmDelete(kb) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${kb.name}」吗？所有文档和索引将被清除，此操作不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
    await deleteKnowledgeBase(kb.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (e) {}
}

onMounted(fetchData)
</script>

<style scoped>
.kb-list-container {
  min-height: 100%;
  padding: 32px 48px;
  background: linear-gradient(180deg, #ecf5ff 0%, #f5f7fa 300px);
}

.kb-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  font-size: 32px;
  color: #409eff;
}

.title {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.kb-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.kb-card {
  cursor: pointer;
  transition: transform 0.2s;
  border-radius: 12px;
}

.kb-card:hover {
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.kb-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.card-desc {
  color: #909399;
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
  margin-bottom: 16px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.card-time {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
