import {
  defaultContextSettings,
  defaultRagRetrievalSettings,
  type ContextMode,
  type ContextSettings,
  type RagRetrievalMode,
  type RagRetrievalSettings,
} from './types'

export const CHAT_MODEL_STORAGE_KEY = 'ai_chat_selected_model_id'
export const CHAT_PROMPT_STORAGE_KEY = 'ai_chat_prompt_type'
export const CHAT_SKILLS_STORAGE_KEY = 'ai_chat_skill_ids'
export const CHAT_DEFAULT_SKILLS_SEEN_STORAGE_KEY = 'ai_chat_default_skill_ids_seen'
export const CHAT_CONTEXT_STORAGE_KEY = 'ai_chat_context_settings'
export const CHAT_RAG_RETRIEVAL_STORAGE_KEY = 'ai_chat_rag_retrieval_settings'

export const readSavedContextSettings = (): ContextSettings => {
  const saved = localStorage.getItem(CHAT_CONTEXT_STORAGE_KEY)
  if (!saved) return defaultContextSettings
  try {
    const parsed = JSON.parse(saved) as Partial<ContextSettings>
    return {
      mode: ['auto', 'low', 'medium', 'high', 'custom', 'current_only'].includes(parsed.mode || '')
        ? parsed.mode as ContextMode
        : defaultContextSettings.mode,
      max_tokens: typeof parsed.max_tokens === 'number' && parsed.max_tokens > 0
        ? parsed.max_tokens
        : defaultContextSettings.max_tokens,
      recent_turns: typeof parsed.recent_turns === 'number' && parsed.recent_turns > 0
        ? parsed.recent_turns
        : defaultContextSettings.recent_turns,
    }
  } catch {
    return defaultContextSettings
  }
}

export const readSavedRagRetrievalSettings = (): RagRetrievalSettings => {
  const saved = localStorage.getItem(CHAT_RAG_RETRIEVAL_STORAGE_KEY)
  if (!saved) return defaultRagRetrievalSettings
  try {
    const parsed = JSON.parse(saved) as Partial<RagRetrievalSettings>
    return {
      mode: ['auto', 'low', 'medium', 'high', 'custom'].includes(parsed.mode || '')
        ? parsed.mode as RagRetrievalMode
        : defaultRagRetrievalSettings.mode,
      knowledge_k: typeof parsed.knowledge_k === 'number' && parsed.knowledge_k > 0
        ? parsed.knowledge_k
        : defaultRagRetrievalSettings.knowledge_k,
      note_k: typeof parsed.note_k === 'number' && parsed.note_k > 0
        ? parsed.note_k
        : defaultRagRetrievalSettings.note_k,
      summary_k: typeof parsed.summary_k === 'number' && parsed.summary_k > 0
        ? parsed.summary_k
        : defaultRagRetrievalSettings.summary_k,
    }
  } catch {
    return defaultRagRetrievalSettings
  }
}

export const readStringArrayStorage = (key: string): string[] => {
  const saved = localStorage.getItem(key)
  if (!saved) return []
  try {
    const parsed = JSON.parse(saved)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

export const readSavedSkillIds = () => readStringArrayStorage(CHAT_SKILLS_STORAGE_KEY)
export const readSeenDefaultSkillIds = () => readStringArrayStorage(CHAT_DEFAULT_SKILLS_SEEN_STORAGE_KEY)

export const formatThinkingDetail = (stage: string, content = '', details?: Record<string, unknown>) => {
  const parts = [`${stage || 'thinking'}: ${content}`]
  if (details?.tool) parts.push(`工具=${String(details.tool)}`)
  if (details?.duration_ms) parts.push(`耗时=${String(details.duration_ms)}ms`)
  if (details?.elapsed_ms) parts.push(`已用=${String(details.elapsed_ms)}ms`)
  if (details?.risk_level) parts.push(`风险=${String(details.risk_level)}`)
  if (details?.stop_reason) parts.push(`停止=${String(details.stop_reason)}`)
  return parts.join(' | ')
}
