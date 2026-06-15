<template>
  <div class="app-wrapper">
    <div class="global-header" v-if="showHeader">
      <div class="header-left">
        <el-icon class="app-logo"><Document /></el-icon>
        <span class="app-title">DocQA 文档智能问答平台</span>
      </div>
      <div class="header-right">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge" :max="99">
          <el-button text class="notification-btn" @click="goToNotifications">
            <el-icon :size="20"><Bell /></el-icon>
          </el-button>
        </el-badge>
      </div>
    </div>
    <div class="main-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Document } from '@element-plus/icons-vue'
import { getUnreadNotificationCount } from '@/api'

const route = useRoute()
const router = useRouter()
const unreadCount = ref(0)
let pollTimer = null

const showHeader = computed(() => {
  return true
})

function goToNotifications() {
  router.push('/notifications')
}

async function loadUnreadCount() {
  try {
    const res = await getUnreadNotificationCount()
    unreadCount.value = res.unread_count || 0
  } catch (e) {
    unreadCount.value = 0
  }
}

onMounted(() => {
  loadUnreadCount()
  pollTimer = setInterval(loadUnreadCount, 30000)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.app-wrapper {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.global-header {
  height: 48px;
  background: linear-gradient(90deg, #409eff 0%, #66b1ff 100%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-logo {
  font-size: 22px;
  color: #fff;
}

.app-title {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.notification-btn {
  color: #fff !important;
}

.notification-btn:hover {
  background: rgba(255,255,255,0.15) !important;
}

.main-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
