export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface UserInfo {
  id?: string
  user_id?: string
  uuid?: string
  username: string
  email: string
  phone?: string
  gender?: string
  bio?: string
  avatar?: string
  date_joined?: string
  is_active?: boolean
}

export interface LoginResponse {
  token: string
  user: UserInfo
}

export interface Note {
  id: string
  user_id: string
  title: string
  content: string
  tags: string[]
  category: string
  is_pinned: boolean
  created_at: string
  updated_at: string
}

export interface NoteListResponse {
  notes: Note[]
  total_count: number
}

export interface NoteTemplate {
  id: string
  user_id: string
  name: string
  icon: string
  category: string
  title: string
  content: string
  tags: string[]
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface NoteStats {
  total: number
  categories: { category: string; count: number }[]
  uncategorized: number
}

export interface DeleteCategoryResponse {
  deleted_count: number
}

export interface ChatSession {
  id: string
  user_id?: string
  title: string
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ChatHistoryMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at?: string | null
}

export type ModelType = 'default' | 'ollama' | 'openai_compatible'

export interface ModelConfig {
  id: string
  user_id: string
  model_type: ModelType
  provider: string
  model_name: string
  base_url: string
  api_key_masked: string
  is_default: boolean
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ModelConfigPayload {
  model_type: ModelType
  provider: string
  model_name: string
  base_url: string
  api_key?: string
  is_default?: boolean
  is_active?: boolean
}

export interface OllamaModelsResponse {
  ok: boolean
  base_url: string
  models: string[]
  error: string
}

export interface ChatMessage {
  id: number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  metadata?: Record<string, unknown>
  created_at: string
}

export interface KnowledgeDocument {
  id: string
  user_id: string
  md5: string
  filename: string
  original_filename?: string
  file_size: number
  file_type?: string
  file_ext?: string
  mime_type?: string
  status: string
  chunk_count: number
  embedding_model?: string
  embedding_provider?: string
  embedding_type?: string
  error_message?: string | null
  created_at: string
  updated_at?: string | null
}

export interface KnowledgeChunk {
  chunk_id: string
  index: number
  content: string
  page: number
  images: string[]
}

export interface KnowledgeDocumentDetail {
  id: string
  user_id: string
  md5: string
  filename: string
  chunk_count: number
  content: string
  images: string[]
  created_at: string | null
  chunks: KnowledgeChunk[]
}

export interface RelatedFragment {
  id: string
  title: string
  content_preview: string
  content: string
  similarity: number
  source: 'knowledge_base' | 'note'
}

export interface BatchIdsRequest {
  ids: string[]
}

export interface BatchCategoryRequest {
  ids: string[]
  category: string
}

export type MemoryType = 'review' | 'todo' | 'reminder' | 'long_term' | 'memo'
export type MemoryStatus = 'active' | 'done' | 'archived'
export type MemoryPriority = 'low' | 'medium' | 'high'

export interface MemoryItem {
  id: string
  user_id?: string
  source_type?: string
  source_id?: string
  type: MemoryType
  title: string
  content?: string
  status: MemoryStatus
  priority: MemoryPriority
  due_at?: string | null
  remind_at?: string | null
  completed_at?: string | null
  archived_at?: string | null
  review_count?: number
  interval_days?: number
  metadata_json?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface MemoryPayload {
  type: MemoryType
  title: string
  content?: string
  priority?: MemoryPriority
  due_at?: string
  remind_at?: string
  source_type?: string
  source_id?: string
}

export interface MemoryQuestion {
  question: string
  choices: string[]
  answer: string
}

export interface MemoryListData {
  memories: MemoryItem[]
  total_count: number
}

export interface SSEMessage {
  type: 'thinking' | 'response' | 'done' | 'error'
  content?: string
  session_id?: string
  stage?: string
  details?: Record<string, unknown>
}

export interface KnowledgeSSEMessage {
  event_type: 'start' | 'queued' | 'processing' | 'slicing_completed' | 'writing' | 'completed' | 'error' | 'finish'
  filename?: string
  progress?: number
  current?: number
  total?: number
  total_files?: number
  file_index?: number
  message?: string
  md5?: string
  knowledge_id?: string
  document_id?: string
  status?: string
  step?: string
  error_message?: string
  chunk_count?: number
  success_count?: number
  failed_count?: number
}

export interface EmbeddingConfig {
  id: string
  user_id: string
  provider: string
  model_type: string
  model_name: string
  base_url: string
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface EmbeddingSwitchResult {
  knowledge_total: number
  knowledge_success: number
  knowledge_failed: number
  knowledge_chunks: number
  note_count: number
  embedding: EmbeddingConfig
}

export interface RerankerConfig {
  provider: string
  model_name: string
  model_path: string
  revision: string
  device: string
  max_length: number
  batch_size: number
  torch_dtype: string
  min_weight_mb: number
  trust_remote_code: boolean
  updated_at?: string | null
}

export interface LocalRerankerModel {
  label: string
  model_name: string
  model_path: string
  complete: boolean
  reason?: string
}
