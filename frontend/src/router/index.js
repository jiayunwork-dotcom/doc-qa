import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    redirect: '/knowledge-bases'
  },
  {
    path: '/knowledge-bases',
    name: 'KnowledgeBaseList',
    component: () => import('@/views/KnowledgeBaseList.vue')
  },
  {
    path: '/knowledge-bases/:id',
    name: 'KnowledgeBaseDetail',
    component: () => import('@/views/KnowledgeBaseDetail.vue')
  },
  {
    path: '/knowledge-bases/:kbId/debug',
    name: 'SearchDebug',
    component: () => import('@/views/SearchDebug.vue')
  },
  {
    path: '/knowledge-bases/:id/compare/:taskId',
    name: 'CompareResult',
    component: () => import('@/views/CompareResult.vue')
  },
  {
    path: '/knowledge-bases/:id/batch-compare/:batchTaskId',
    name: 'BatchCompareOverview',
    component: () => import('@/views/BatchCompareOverview.vue')
  },
  {
    path: '/knowledge-bases/:kbId/documents/:docId/versions',
    name: 'DocumentVersions',
    component: () => import('@/views/DocumentVersions.vue')
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/Notifications.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
