<template>
  <div class="notifications-container">
    <div class="top-navbar">
      <div class="nav-left">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-divider direction="vertical" />
        <span class="page-title">通知中心</span>
        <el-tag v-if="unreadCount > 0" type="danger" size="small" effect="dark">
          {{ unreadCount }} 条未读
        </el-tag>
      </div>
      <div class="nav-right">
        <el-button
          type="primary"
          size="small"
          :disabled="unreadCount === 0"
          @click="markAllRead"
        >
          <el-icon><Check /></el-icon> 全部标记已读
        </el-button>
        <el-button size="small" @click="refreshData">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-radio-group v-model="filterStatus" size="small" @change="loadNotifications">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="unread">未读</el-radio-button>
        <el-radio-button label="read">已读</el-radio-button>
      </el-radio-group>
    </div>

    <div class="notifications-content">
      <el-empty v-if="loading" description="加载中..." :image-size="60" />
      <el-empty
        v-else-if="notifications.length === 0"
        :description="filterStatus === 'unread' ? '暂无未读通知' : '暂无通知'"
        :image-size="100"
      >
        <template #image>
          <el-icon :size="60" color="#c0c4cc"><Bell /></el-icon>
        </template>
      </el-empty>

      <div v-else class="notification-list">
        <div
          v-for="item in notifications"
          :key="item.id"
          class="notification-item"
          :class="{ 'is-unread': !item.is_read }"
          @click="handleNotificationClick(item)"
        >
          <div class="notif-left">
            <div class="notif-icon" :class="getNotifIconClass(item)">
              <el-icon><UploadFilled /></el-icon>
            </div>
          </div>
          <div class="notif-content">
            <div class="notif-header">
              <span class="notif-doc-name">{{ item.document_name }}</span>
              <el-tag size="small" type="primary">v{{ item.version }}</el-tag>
              <el-tag
                v-if="!item.is_read"
                size="small"
                type="danger"
                effect="plain"
                class="unread-tag"
              >
                未读
              </el-tag>
              <span class="notif-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="notif-body">
              <template v-if="item.change_summary?.rollback">
                <span class="rollback-text">
                  <el-icon><RefreshLeft /></el-icon>
                  从 v{{ item.change_summary.from_version }} 回退到 v{{ item.change_summary.to_version }}
                </span>
              </template>
              <template v-else>
                <span class="change-summary">
                  变更摘要：
                  <span class="add" v-if="item.change_summary?.added > 0">
                    新增 {{ item.change_summary.added }} 段
                  </span>
                  <span class="del" v-if="item.change_summary?.deleted > 0">
                    删除 {{ item.change_summary.deleted }} 段
                  </span>
                  <span class="total">
                    当前共 {{ item.change_summary?.total_current || 0 }} 段
                  </span>
                </span>
              </template>
            </div>
          </div>
          <div class="notif-actions" @click.stop>
            <el-button
              v-if="!item.is_read"
              size="small"
              text
              type="primary"
              @click="markAsRead(item)"
            >
              标记已读
            </el-button>
            <el-button size="small" text type="danger" @click="deleteNotif(item)">
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Check, Refresh, Bell, UploadFilled, RefreshLeft
} from '@element-plus/icons-vue'
import {
  listNotifications, getUnreadNotificationCount,
  markNotificationRead, markAllNotificationsRead, deleteNotification
} from '@/api'

const router = useRouter()
const notifications = ref([])
const loading = ref(false)
const unreadCount = ref(0)
const filterStatus = ref('all')

function goBack() {
  router.push('/knowledge-bases')
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diff = now - d
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function getNotifIconClass(item) {
  if (item.change_summary?.rollback) return 'rollback'
  return 'update'
}

async function refreshData() {
  await Promise.all([loadNotifications(), loadUnreadCount()])
}

async function loadNotifications() {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value === 'unread') {
      params.only_unread = true
    }
    const list = await listNotifications(params)
    if (filterStatus.value === 'read') {
      notifications.value = list.filter(n => n.is_read)
    } else {
      notifications.value = list
    }
  } finally {
    loading.value = false
  }
}

async function loadUnreadCount() {
  try {
    const res = await getUnreadNotificationCount()
    unreadCount.value = res.unread_count || 0
  } catch (e) {
    unreadCount.value = 0
  }
}

async function handleNotificationClick(item) {
  if (!item.is_read) {
    await markAsRead(item)
  }
  router.push(`/knowledge-bases/${item.knowledge_base_id}/documents/${item.document_id}/versions`)
}

async function markAsRead(item) {
  try {
    await markNotificationRead(item.id)
    item.is_read = true
    await loadUnreadCount()
  } catch (e) {
    ElMessage.error('标记失败')
  }
}

async function markAllRead() {
  try {
    await ElMessageBox.confirm('确定将所有通知标记为已读吗？', '确认', { type: 'info' })
    await markAllNotificationsRead({ all: true })
    notifications.value.forEach(n => n.is_read = true)
    unreadCount.value = 0
    ElMessage.success('已全部标记为已读')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('操作失败')
    }
  }
}

async function deleteNotif(item) {
  try {
    await ElMessageBox.confirm('确定删除这条通知吗？', '删除确认', { type: 'warning' })
    await deleteNotification(item.id)
    notifications.value = notifications.value.filter(n => n.id !== item.id)
    if (!item.is_read) {
      await loadUnreadCount()
    }
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  refreshData()
})
</script>

<style scoped>
.notifications-container {
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

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-right: 8px;
}

.filter-bar {
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.notifications-content {
  flex: 1;
  padding: 16px 20px;
  overflow: auto;
}

.notification-list {
  max-width: 900px;
  margin: 0 auto;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s;
}

.notification-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}

.notification-item.is-unread {
  background: #fafcff;
  border-left: 3px solid #409eff;
}

.notif-left {
  flex-shrink: 0;
}

.notif-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.notif-icon.update {
  background: #ecf5ff;
  color: #409eff;
}

.notif-icon.rollback {
  background: #fdf6ec;
  color: #e6a23c;
}

.notif-content {
  flex: 1;
  min-width: 0;
}

.notif-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.notif-doc-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.unread-tag {
  margin-left: 4px;
}

.notif-time {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.notif-body {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.change-summary .add {
  color: #67c23a;
  margin: 0 6px;
}

.change-summary .del {
  color: #f56c6c;
  margin: 0 6px;
}

.change-summary .total {
  color: #909399;
  margin: 0 6px;
}

.rollback-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #e6a23c;
  font-weight: 500;
}

.notif-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.notification-item:hover .notif-actions {
  opacity: 1;
}
</style>
