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
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
