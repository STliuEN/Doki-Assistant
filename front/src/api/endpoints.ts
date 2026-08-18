export const endpoints = {
  // Auth
  login: '/user/login/',
  refreshToken: '/user/refresh-token/',
  logout: '/user/logout/',
  register: '/user/register/',
  profile: '/user/detail/',
  userUpdate: '/user/update/',
  changePassword: '/user/reset-password/',

  // File upload
  uploadFile: '/file/upload/',

  // AI Chat
  agentQueryStream: '/chat/agent/query/stream',
  chatPromptModes: '/chat/prompt-modes',
  chatSkills: '/api/chat/skills',
  ragQuery: '/chat/rag/query',
  dialogueTranslateStream: '/translate/dialogue/stream',

  // Skills
  skillCatalog: '/api/skills/catalog',
  skillDetail: (id: string) => `/api/skills/${id}`,
  skillCreate: '/api/skills',
  skillUpdate: (id: string) => `/api/skills/${id}`,
  skillDelete: (id: string) => `/api/skills/${id}`,

  toolCatalog: '/api/tools/catalog',
  toolCreate: '/api/tools',
  toolUpdate: (id: string) => `/api/tools/${id}`,
  toolDelete: (id: string) => `/api/tools/${id}`,

  mcpServers: '/api/mcp/servers',
  mcpPermissions: '/api/mcp/permissions',
  mcpRefreshAll: '/api/mcp/servers/refresh',
  mcpServerUpdate: (id: string) => `/api/mcp/servers/${id}`,
  mcpServerDelete: (id: string) => `/api/mcp/servers/${id}`,
  mcpTools: '/api/mcp/tools',
  mcpToolUpdate: (id: string) => `/api/mcp/tools/${id}`,
  mcpToolDelete: (id: string) => `/api/mcp/tools/${id}`,

  // Model Config
  modelConfigList: '/model-config/list',
  modelConfigSystemDefault: '/model-config/system-default',
  modelConfigCreate: '/model-config/create',
  modelConfigUpdate: (id: string) => `/model-config/${id}`,
  modelConfigDelete: (id: string) => `/model-config/${id}`,
  modelConfigSetDefault: (id: string) => `/model-config/${id}/set-default`,
  modelConfigTest: '/model-config/test',
  modelConfigTestSystemDefault: '/model-config/system-default/test',
  modelConfigTestSaved: (id: string) => `/model-config/${id}/test`,
  modelConfigOllamaModels: '/model-config/ollama/models',

  // Sessions
  getSession: (id: string) => `/chat/session/${id}`,
  getSessionMessages: (id: string) => `/chat/session/${id}/messages`,
  deleteSessionMessage: (sessionId: string, messageId: number, mode = 'single') => (
    `/chat/session/${sessionId}/messages/${messageId}?mode=${encodeURIComponent(mode)}`
  ),
  regenerateSessionMessage: (sessionId: string, messageId: number) => (
    `/chat/session/${sessionId}/messages/${messageId}/regenerate/stream`
  ),
  deleteSession: (id: string) => `/chat/session/${id}`,
  getAllSessions: '/chat/sessions',
  getUserSessions: (userId: string) => `/chat/sessions/${userId}`,

  // Knowledge Base
  uploadSingleFile: '/knowledge/add/single',
  uploadMultipleFiles: '/knowledge/add/multiple',
  uploadMultipleStream: '/knowledge/add/multiple/stream',
  cleanVectors: '/knowledge/clean',
  knowledgeList: '/knowledge/list',
  knowledgeDetail: '/knowledge/detail',
  knowledgeChunks: '/knowledge/chunks',
  knowledgeSource: '/knowledge/source',
  knowledgeImage: (md5: string, filename: string) => `/knowledge/image/${md5}/${filename}`,
  knowledgeMd5List: '/knowledge/md5/list',
  knowledgeMd5Delete: (md5: string) => `/knowledge/md5/delete/${md5}`,
  knowledgeDeleteFilename: '/knowledge/delete/filename',
  knowledgeEmbeddingCurrent: '/knowledge/embedding/current',
  knowledgeEmbeddingOllamaModels: '/knowledge/embedding/ollama/models',
  knowledgeEmbeddingSwitch: '/knowledge/embedding/switch',
  knowledgeRerankerCurrent: '/knowledge/reranker/current',
  knowledgeRerankerLocalModels: '/knowledge/reranker/local-models',
  knowledgeRerankerSwitch: '/knowledge/reranker/switch',

  // Documents reorder
  reorderDocuments: '/chat/reorder',

  // Notes
  noteCreate: '/note/create',
  noteUpdate: (id: string) => `/note/${id}`,
  noteDelete: (id: string) => `/note/${id}`,
  noteDetail: (id: string) => `/note/${id}`,
  noteList: '/note/list',
  noteSearch: '/note/search',
  noteAutoTag: (id: string) => `/note/${id}/auto-tag`,
  noteRelated: (id: string) => `/note/${id}/related`,
  noteDownload: (id: string) => `/note/${id}/download`,
  notePin: (id: string) => `/note/${id}/pin`,
  noteAutocomplete: '/note/autocomplete',
  noteStats: '/note/stats',
  noteAssistStream: '/note/assist/stream',

  // Batch operations
  noteBatchDelete: '/note/batch/delete',
  noteBatchDownload: '/note/batch/download',
  noteBatchCategory: '/note/batch/category',
  noteBatchPin: '/note/batch/pin',
  noteCategoryDelete: (category: string) => `/note/category/${encodeURIComponent(category)}`,

  // Memory
  memoryToday: '/memory/today',
  memoryList: '/memory/list',
  memoryDetail: (id: string) => `/memory/${id}`,
  memoryCreate: '/memory/create',
  memoryUpdate: (id: string) => `/memory/${id}`,
  memoryComplete: (id: string) => `/memory/${id}/complete`,
  memoryReviewed: (id: string) => `/memory/${id}/reviewed`,
  memoryPostpone: (id: string) => `/memory/${id}/postpone`,
  memoryArchive: (id: string) => `/memory/${id}/archive`,
  memoryDelete: (id: string) => `/memory/${id}`,
  memoryReviewQuestion: (id: string) => `/memory/${id}/review-question`,

  // Note Templates
  noteTemplateList: '/note-template/list',
  noteTemplateCreate: '/note-template/create',
  noteTemplateUpdate: (id: string) => `/note-template/${id}`,
  noteTemplateDelete: (id: string) => `/note-template/${id}`,
  noteTemplateReorder: '/note-template/reorder',
} as const
