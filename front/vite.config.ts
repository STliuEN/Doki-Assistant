import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const BACKEND_TARGET = process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:18000'
const USER_TARGET = process.env.VITE_USER_TARGET || 'http://127.0.0.1:18001'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // 端口固定在 Windows 动态端口区（1024-15000）之外，避免重启后被系统保留段征用。
    // strictPort: true 表示端口被占用时直接报错，而不是静默顺延到别的端口。
    port: 18080,
    strictPort: true,
    host: '0.0.0.0',
    proxy: {
      '/chat/agent/': { target: BACKEND_TARGET, changeOrigin: true, ws: true },
      '/chat/rag/': { target: BACKEND_TARGET, changeOrigin: true },
      '/chat/session/': { target: BACKEND_TARGET, changeOrigin: true },
      '/chat/sessions': { target: BACKEND_TARGET, changeOrigin: true },
      '/chat/prompt-modes': { target: BACKEND_TARGET, changeOrigin: true },
      '/chat/reorder': { target: BACKEND_TARGET, changeOrigin: true },
      '/api/chat/skills': {
        target: BACKEND_TARGET,
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
      '/api/skills': {
        target: BACKEND_TARGET,
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
      '/api/tools': {
        target: BACKEND_TARGET,
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
      '/api/mcp': { target: BACKEND_TARGET, changeOrigin: true },
      '/knowledge/': { target: BACKEND_TARGET, changeOrigin: true },
      '/note/': { target: BACKEND_TARGET, changeOrigin: true },
      '/note-template/': { target: BACKEND_TARGET, changeOrigin: true },
      '/memory/': { target: BACKEND_TARGET, changeOrigin: true },
      '/model-config/': { target: BACKEND_TARGET, changeOrigin: true },
      '/translate/': { target: BACKEND_TARGET, changeOrigin: true },
      '/health': { target: BACKEND_TARGET, changeOrigin: true },
      '/user': { target: USER_TARGET, changeOrigin: true },
      '/file': { target: USER_TARGET, changeOrigin: true },
    },
  },
})
