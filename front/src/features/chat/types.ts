export interface Message {
  id?: number
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  steps?: string[]
}

export type ContextMode = 'auto' | 'low' | 'medium' | 'high' | 'custom' | 'current_only'
export type RagRetrievalMode = 'auto' | 'low' | 'medium' | 'high' | 'custom'

export interface ContextSettings {
  mode: ContextMode
  max_tokens: number
  recent_turns: number
}

export interface RagRetrievalSettings {
  mode: RagRetrievalMode
  knowledge_k: number
  note_k: number
  summary_k: number
}

export type PendingConfirmation = {
  pendingActionId: string
  tool?: string
  content?: string
  inputPreview?: string
}

export const defaultContextSettings: ContextSettings = {
  mode: 'auto',
  max_tokens: 4000,
  recent_turns: 6,
}

export const defaultRagRetrievalSettings: RagRetrievalSettings = {
  mode: 'auto',
  knowledge_k: 6,
  note_k: 3,
  summary_k: 3,
}

export const quickQuestions = [
  '帮我写一篇关于机器学习的笔记',
  '总结一下今天要复习的内容',
  'RAG 是什么？',
]
