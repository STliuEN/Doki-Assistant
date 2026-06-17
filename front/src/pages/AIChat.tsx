import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Send, Sparkles, Bot, User, ChevronDown, ChevronRight, Loader2, Wrench, Trash2, RefreshCw, Gauge } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'
import { useSSE } from '../hooks/useSSE'
import { chatApi, type ChatPromptMode, type ChatSkill, type ChatTool } from '../api/chat'
import { modelConfigApi } from '../api/modelConfig'
import { sessionsApi } from '../api/sessions'
import { useThemeStore } from '../stores/useThemeStore'
import type { ModelConfig } from '../types/api'
import { endpoints } from '../api/endpoints'

interface Message {
  id?: number
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  steps?: string[]
}

const CHAT_MODEL_STORAGE_KEY = 'ai_chat_selected_model_id'
const CHAT_PROMPT_STORAGE_KEY = 'ai_chat_prompt_type'
const CHAT_SKILLS_STORAGE_KEY = 'ai_chat_skill_ids'
const CHAT_CONTEXT_STORAGE_KEY = 'ai_chat_context_settings'
const CHAT_RAG_RETRIEVAL_STORAGE_KEY = 'ai_chat_rag_retrieval_settings'

type ContextMode = 'auto' | 'low' | 'medium' | 'high' | 'custom' | 'current_only'
type RagRetrievalMode = 'auto' | 'low' | 'medium' | 'high' | 'custom'

interface ContextSettings {
  mode: ContextMode
  max_tokens: number
  recent_turns: number
}

interface RagRetrievalSettings {
  mode: RagRetrievalMode
  knowledge_k: number
  note_k: number
  summary_k: number
}

const defaultContextSettings: ContextSettings = {
  mode: 'auto',
  max_tokens: 4000,
  recent_turns: 6,
}

const defaultRagRetrievalSettings: RagRetrievalSettings = {
  mode: 'auto',
  knowledge_k: 6,
  note_k: 3,
  summary_k: 3,
}

const readSavedContextSettings = (): ContextSettings => {
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

const readSavedRagRetrievalSettings = (): RagRetrievalSettings => {
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

const readSavedSkillIds = () => {
  const saved = localStorage.getItem(CHAT_SKILLS_STORAGE_KEY)
  if (!saved) return []
  try {
    const parsed = JSON.parse(saved)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

const quickQuestions = [
  '帮我写一篇关于机器学习的笔记',
  '总结一下今天要复习的内容',
  'RAG 是什么？',
]

export default function AIChat() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const theme = useThemeStore((s) => s.theme)
  const { start, loading } = useSSE()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [currentThinking, setCurrentThinking] = useState('')
  const [currentSteps, setCurrentSteps] = useState<string[]>([])
  const [currentStepDetails, setCurrentStepDetails] = useState<string[]>([])
  const [showThinking, setShowThinking] = useState(true)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([])
  const [promptModes, setPromptModes] = useState<ChatPromptMode[]>([
    { value: 'main_prompt', label: '默认助手' },
  ])
  const [skills, setSkills] = useState<ChatSkill[]>([])
  const [tools, setTools] = useState<ChatTool[]>([])
  const [toolsById, setToolsById] = useState<Record<string, ChatTool>>({})
  const [showToolPanel, setShowToolPanel] = useState(false)
  const [showContextPanel, setShowContextPanel] = useState(false)
  const [skillSelectionTouched, setSkillSelectionTouched] = useState(() => (
    localStorage.getItem(CHAT_SKILLS_STORAGE_KEY) !== null
  ))
  const [skillCatalogLoaded, setSkillCatalogLoaded] = useState(false)
  const [skillCatalogError, setSkillCatalogError] = useState('')
  const [selectedModelId, setSelectedModelId] = useState(() => localStorage.getItem(CHAT_MODEL_STORAGE_KEY) || '')
  const [selectedPromptType, setSelectedPromptType] = useState(() => localStorage.getItem(CHAT_PROMPT_STORAGE_KEY) || 'main_prompt')
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>(readSavedSkillIds)
  const [contextSettings, setContextSettings] = useState<ContextSettings>(readSavedContextSettings)
  const [ragRetrievalSettings, setRagRetrievalSettings] = useState<RagRetrievalSettings>(readSavedRagRetrievalSettings)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef('')
  const regeneratingMessageIdRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  const flushContent = useCallback(() => {
    setMessages((prev) => {
      if (regeneratingMessageIdRef.current !== null) {
        return prev.map((message) => (
          message.id === regeneratingMessageIdRef.current
            ? { ...message, content: contentRef.current }
            : message
        ))
      }
      const newMsgs = [...prev]
      const last = newMsgs[newMsgs.length - 1]
      if (last?.role === 'assistant') {
        newMsgs[newMsgs.length - 1] = { ...last, content: contentRef.current }
      } else {
        newMsgs.push({ role: 'assistant', content: contentRef.current })
      }
      return newMsgs
    })
  }, [])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    modelConfigApi.list().then((res) => {
      const list = res.data || []
      setModelConfigs(list)
    }).catch(() => {})
    chatApi.promptModes().then((res) => {
      const list = res.data || []
      if (list.length > 0) setPromptModes(list)
    }).catch(() => {})
    chatApi.skillCatalog().then((res) => {
      const catalog = res.data
      if (!catalog) return
      const nextSkills = catalog.skills || []
      const defaultSkillIds = catalog.default_skill_ids || []
      const validSkillIds = new Set(nextSkills.map((skill) => skill.id))
      setSkills(nextSkills)
      setTools(catalog.tools || [])
      setToolsById(Object.fromEntries((catalog.tools || []).map((tool) => [tool.id, tool])))
      setSelectedSkillIds((current) => {
        const validCurrent = current.filter((id) => validSkillIds.has(id))
        return validCurrent.length > 0 ? validCurrent : defaultSkillIds
      })
      setSkillCatalogError('')
      setSkillCatalogLoaded(true)
    }).catch((error) => {
      console.error('Failed to load skill catalog', error)
      setSkillCatalogError('Skill 列表暂时不可用')
      setSkillCatalogLoaded(true)
    })
  }, [])

  useEffect(() => {
    localStorage.setItem(CHAT_MODEL_STORAGE_KEY, selectedModelId)
  }, [selectedModelId])

  useEffect(() => {
    localStorage.setItem(CHAT_PROMPT_STORAGE_KEY, selectedPromptType)
  }, [selectedPromptType])

  useEffect(() => {
    localStorage.setItem(CHAT_SKILLS_STORAGE_KEY, JSON.stringify(selectedSkillIds))
  }, [selectedSkillIds])

  useEffect(() => {
    localStorage.setItem(CHAT_CONTEXT_STORAGE_KEY, JSON.stringify(contextSettings))
  }, [contextSettings])

  useEffect(() => {
    localStorage.setItem(CHAT_RAG_RETRIEVAL_STORAGE_KEY, JSON.stringify(ragRetrievalSettings))
  }, [ragRetrievalSettings])

  const toggleSkill = useCallback((skillId: string) => {
    setSkillSelectionTouched(true)
    setSelectedSkillIds((current) => (
      current.includes(skillId)
        ? current.filter((id) => id !== skillId)
        : [...current, skillId]
    ))
  }, [])

  const loadSessionMessages = useCallback(async (id: string) => {
    const res = await sessionsApi.messages(id)
    const data = res.data
    if (data?.messages) {
      setMessages(data.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
      })))
    }
  }, [])

  useEffect(() => {
    if (sessionId) {
      setLoadingHistory(true)
      loadSessionMessages(sessionId).catch(() => {}).finally(() => setLoadingHistory(false))
    }
  }, [loadSessionMessages, sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentThinking])

  useEffect(() => {
    if (!sessionId) {
      const lastId = sessionStorage.getItem('lastSessionId')
      if (lastId) {
        navigate(`/chat/${lastId}`, { replace: true })
      }
    }
  }, [sessionId, navigate])

  const handleSend = useCallback(async (query: string) => {
    if (!query.trim() || loading) return

    const userMsg: Message = { role: 'user', content: query }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setCurrentThinking('')
    setCurrentSteps([])
    setCurrentStepDetails(['请求已发送，等待 Agent 开始执行...'])
    setShowThinking(true)

    contentRef.current = ''
    regeneratingMessageIdRef.current = null
    const steps: string[] = []
    let hasResponseStarted = false

    await start(
      '/chat/agent/query/stream',
      {
        query,
        session_id: sessionId,
        prompt_type: selectedPromptType,
        context: contextSettings,
        rag_retrieval: ragRetrievalSettings,
        ...(skillSelectionTouched ? { skill_ids: selectedSkillIds, tool_ids: [] } : {}),
        ...(selectedModelId ? { model_config_id: selectedModelId } : {}),
      },
      {
        onThinking: (stage, content) => {
          if (!steps.includes(stage)) steps.push(stage)
          setCurrentSteps([...steps])
          setCurrentThinking(content || '')
          setCurrentStepDetails((current) => [
            ...current,
            `${stage || 'thinking'}: ${content || ''}`,
          ])
        },
        onResponse: (content, sessionId) => {
          if (!hasResponseStarted) {
            hasResponseStarted = true
            setShowThinking(false)
          }
          if (sessionId) {
            sessionStorage.setItem('lastSessionId', sessionId)
          }
          contentRef.current += content
          if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
              rafRef.current = null
              flushContent()
            })
          }
        },
        onDone: (newSessionId) => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          flushContent()
          if (newSessionId) {
            sessionStorage.setItem('lastSessionId', newSessionId)
          }
          if (newSessionId && newSessionId !== sessionId) {
            navigate(`/chat/${newSessionId}`, { replace: true })
          } else if (sessionId) {
            void loadSessionMessages(sessionId)
          }
        },
        onError: (error) => {
          setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${error}` }])
        },
      }
    )
  }, [contextSettings, loadSessionMessages, loading, ragRetrievalSettings, sessionId, selectedModelId, selectedPromptType, selectedSkillIds, skillSelectionTouched, start, navigate, flushContent])

  const handleRegenerateMessage = useCallback(async (message: Message) => {
    if (!sessionId || !message.id || message.role !== 'assistant' || loading) return

    setCurrentThinking('')
    setCurrentSteps([])
    setCurrentStepDetails(['正在请求重新生成...'])
    setShowThinking(true)
    contentRef.current = ''
    regeneratingMessageIdRef.current = message.id
    setMessages((prev) => prev.map((item) => (
      item.id === message.id ? { ...item, content: '' } : item
    )))

    const steps: string[] = []
    let hasResponseStarted = false

    await start(
      endpoints.regenerateSessionMessage(sessionId, message.id),
      {
        prompt_type: selectedPromptType,
        context: contextSettings,
        rag_retrieval: ragRetrievalSettings,
        ...(skillSelectionTouched ? { skill_ids: selectedSkillIds, tool_ids: [] } : {}),
        ...(selectedModelId ? { model_config_id: selectedModelId } : {}),
      },
      {
        onThinking: (stage, content) => {
          if (!steps.includes(stage)) steps.push(stage)
          setCurrentSteps([...steps])
          setCurrentThinking(content || '')
          setCurrentStepDetails((current) => [
            ...current,
            `${stage || 'thinking'}: ${content || ''}`,
          ])
        },
        onResponse: (content) => {
          if (!hasResponseStarted) {
            hasResponseStarted = true
            setShowThinking(false)
          }
          contentRef.current += content
          if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
              rafRef.current = null
              flushContent()
            })
          }
        },
        onDone: () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          flushContent()
          regeneratingMessageIdRef.current = null
        },
        onError: (error) => {
          setMessages((prev) => prev.map((item) => (
            item.id === message.id ? { ...item, content: `Error: ${error}` } : item
          )))
          regeneratingMessageIdRef.current = null
        },
      }
    )
  }, [contextSettings, flushContent, loading, ragRetrievalSettings, selectedModelId, selectedPromptType, selectedSkillIds, sessionId, skillSelectionTouched, start])

  const handleDeleteMessage = useCallback(async (message: Message) => {
    if (!sessionId || !message.id || loading) return
    const mode = message.role === 'user' ? 'pair' : 'single'
    const confirmed = window.confirm(message.role === 'user' ? '确定删除这条提问及紧随其后的回答吗？' : '确定删除这条回答吗？')
    if (!confirmed) return
    try {
      const res = await sessionsApi.deleteMessage(sessionId, message.id, mode)
      const deletedIds = new Set(res.data?.deleted_ids || [])
      setMessages((prev) => prev.filter((item) => !item.id || !deletedIds.has(item.id)))
    } catch {
      setMessages((prev) => prev)
    }
  }, [loading, sessionId])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(input)
    }
  }

  const isLoading = loadingHistory || loading
  const hasStreamingAssistant = loading && messages.length > 0 && messages[messages.length - 1].role === 'assistant'

  return (
    <div className="h-full flex flex-col">
      {messages.length > 0 && (
        <div className="shrink-0 px-6 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]">
          <div className="max-w-3xl mx-auto flex justify-end">
            <button
              onClick={() => {
                sessionStorage.removeItem('lastSessionId')
                setMessages([])
                navigate('/chat')
              }}
              className="px-3 py-1.5 text-xs rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
            >
              {t('chat.newSession')}
            </button>
          </div>
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && !isLoading && (
            <div className="py-16 text-center space-y-6">
              <div className="flex justify-center">
                <div className="w-16 h-16 rounded-2xl bg-[var(--color-accent-bg)] flex items-center justify-center">
                  <Sparkles size={28} className="text-[var(--color-accent)]" />
                </div>
              </div>
              <h2 className="font-heading text-xl text-[var(--color-text)]">{t('chat.welcome')}</h2>
              <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
                {quickQuestions.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSend(q)}
                    className="px-4 py-2 text-xs rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {loadingHistory && (
            <div className="flex justify-center py-4">
              <Loader2 size={20} className="animate-spin text-[var(--color-text-tertiary)]" />
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={msg.id ?? i} className={`group flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-[var(--color-accent-bg)] flex items-center justify-center shrink-0">
                  <Bot size={16} className="text-[var(--color-accent)]" />
                </div>
              )}
              <div className={`max-w-[75%] ${msg.role === 'user' ? 'order-first' : ''}`}>
                {msg.role === 'user' ? (
                  <div className="space-y-1">
                    <div className="px-4 py-2.5 rounded-2xl bg-[var(--color-accent)] text-white text-sm">
                      {msg.content}
                    </div>
                    {msg.id && (
                      <div className="flex justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => void handleDeleteMessage(msg)}
                          disabled={loading}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] disabled:opacity-50"
                          title="删除"
                        >
                          <Trash2 size={13} />
                          删除
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    {i === messages.length - 1 && currentSteps.length > 0 && (
                      <div className="mb-3">
                        <div className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                          <button
                            onClick={() => setShowThinking(!showThinking)}
                            className="flex items-center gap-2 px-4 py-2.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] w-full text-left"
                          >
                            {showThinking ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            {t('chat.thinkingSteps')}
                          </button>
                          {showThinking && currentStepDetails.length > 0 && (
                            <div className="px-4 pb-3 space-y-1">
                              {currentStepDetails.map((detail, detailIndex) => (
                                <p key={`${detailIndex}-${detail}`} className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                                  {detail}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    <div className={`prose prose-sm max-w-none markdown-body${theme === 'dark' ? ' prose-invert' : ''}`}>
                      <ReactMarkdown rehypePlugins={[rehypeHighlight, rehypeRaw]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                    {hasStreamingAssistant && i === messages.length - 1 && (
                      <div className="flex gap-1 mt-3">
                        <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    )}
                    {msg.id && (
                      <div className="mt-2 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => void handleRegenerateMessage(msg)}
                          disabled={loading}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] disabled:opacity-50"
                          title="重新生成"
                        >
                          <RefreshCw size={13} />
                          刷新
                        </button>
                        <button
                          onClick={() => void handleDeleteMessage(msg)}
                          disabled={loading}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] disabled:opacity-50"
                          title="删除"
                        >
                          <Trash2 size={13} />
                          删除
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-[var(--color-bg-tertiary)] flex items-center justify-center shrink-0">
                  <User size={16} className="text-[var(--color-text-secondary)]" />
                </div>
              )}
            </div>
          ))}

          {loading && !hasStreamingAssistant && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-[var(--color-accent-bg)] flex items-center justify-center shrink-0">
                <Bot size={16} className="text-[var(--color-accent)]" />
              </div>
              <div className="space-y-2 flex-1">
                {currentStepDetails.length > 0 && (
                  <div className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                    <button
                      onClick={() => setShowThinking(!showThinking)}
                      className="flex items-center gap-2 px-4 py-2.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] w-full text-left"
                    >
                      {showThinking ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      {t('chat.thinkingSteps')}
                    </button>
                    {showThinking && (
                      <div className="px-4 pb-3 space-y-1">
                        {currentStepDetails.map((detail, detailIndex) => (
                          <p key={`${detailIndex}-${detail}`} className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                            {detail}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4">
        <div className="max-w-3xl mx-auto space-y-2">
          <div className="flex flex-wrap items-center justify-start gap-2 text-xs text-[var(--color-text-secondary)]">
            <div className="flex w-[300px] max-w-full items-center gap-1.5 min-w-0">
              <span className="w-7 shrink-0 text-right">模型</span>
              <select
                value={selectedModelId}
                onChange={(e) => setSelectedModelId(e.target.value)}
                className="h-8 flex-1 min-w-0 px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)]"
              >
                <option value="">工程默认配置</option>
                {modelConfigs.map((config) => (
                  <option key={config.id} value={config.id}>
                    {[config.provider, config.model_name].filter(Boolean).join(' / ') || '未命名模型'}
                    {config.is_default ? '（默认）' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex w-[150px] items-center gap-1.5 shrink-0">
              <span className="w-10 shrink-0 text-right">AI模式</span>
              <select
                value={selectedPromptType}
                onChange={(e) => setSelectedPromptType(e.target.value)}
                className="h-8 w-[102px] px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)]"
              >
                {promptModes.map((mode) => (
                  <option key={mode.value} value={mode.value}>{mode.label}</option>
                ))}
              </select>
            </div>
            <div className="relative w-[92px] shrink-0">
              <button
                type="button"
                onClick={() => setShowToolPanel((value) => !value)}
                className="h-8 w-full inline-flex items-center justify-center gap-1.5 px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)] hover:border-[var(--color-accent)] transition-colors"
              >
                <Wrench size={13} />
                <span className="w-7 text-left">Skill</span>
                <span className="w-4 text-right text-[var(--color-text-tertiary)]">
                  {selectedSkillIds.length}
                </span>
              </button>
              {showToolPanel && (
                <div className="absolute right-0 bottom-10 z-20 w-[360px] max-w-[calc(100vw-48px)] rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] shadow-lg p-3 space-y-3">
                  {skills.length === 0 && tools.length === 0 ? (
                    <div className="text-xs text-[var(--color-text-secondary)]">
                      {skillCatalogLoaded ? skillCatalogError || '暂无可用 Skill。' : '正在加载 Skill...'}
                    </div>
                  ) : (
                    <>
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-[var(--color-text)]">Skill</span>
                      <span className="text-[var(--color-text-secondary)]">
                        已启用 {selectedSkillIds.length} / {skills.length}
                      </span>
                    </div>
                    {skills.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
                          <span>技能</span>
                          <button
                            type="button"
                            onClick={() => {
                              setSkillSelectionTouched(true)
                              setSelectedSkillIds(skills.map((skill) => skill.id))
                            }}
                            className="text-[var(--color-accent)] hover:underline"
                          >
                            全选
                          </button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {skills.map((skill) => {
                            const active = selectedSkillIds.includes(skill.id)
                            const toolLabels = skill.tool_ids
                              .map((toolId) => toolsById[toolId]?.label)
                              .filter(Boolean)
                              .join(' / ')
                            return (
                              <button
                                key={skill.id}
                                type="button"
                                onClick={() => toggleSkill(skill.id)}
                                title={`${skill.description}${toolLabels ? `\n工具: ${toolLabels}` : ''}`}
                                className={`px-2.5 py-1.5 rounded-md border text-xs transition-colors ${
                                  active
                                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                                    : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]'
                                }`}
                              >
                                {skill.label}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    </>
                  )}
                </div>
              )}
            </div>
            <div className="relative w-[88px] shrink-0">
              <button
                type="button"
                onClick={() => setShowContextPanel((value) => !value)}
                className="h-8 w-full inline-flex items-center justify-center gap-1.5 px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)] hover:border-[var(--color-accent)] transition-colors"
                title="策略设置"
              >
                <Gauge size={13} />
                <span>策略</span>
              </button>
              {showContextPanel && (
                <div className="absolute right-0 bottom-10 z-20 w-[360px] max-w-[calc(100vw-48px)] rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] shadow-lg p-3 space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-[var(--color-text)]">上下文长度</span>
                      <span className="text-[var(--color-text-secondary)]">按 token 估算裁剪</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { value: 'auto', label: 'Auto' },
                        { value: 'low', label: '低' },
                        { value: 'medium', label: '中' },
                        { value: 'high', label: '高' },
                        { value: 'custom', label: '自定义' },
                        { value: 'current_only', label: '仅当前' },
                      ].map((mode) => {
                        const active = contextSettings.mode === mode.value
                        return (
                          <button
                            key={mode.value}
                            type="button"
                            onClick={() => setContextSettings((current) => ({
                              ...current,
                              mode: mode.value as ContextMode,
                              max_tokens: mode.value === 'low'
                                ? 2000
                                : mode.value === 'medium'
                                  ? 4000
                                  : mode.value === 'high'
                                    ? 8000
                                    : current.max_tokens,
                            }))}
                            className={`h-8 rounded-md border text-xs transition-colors ${
                              active
                                ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                                : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]'
                            }`}
                          >
                            {mode.label}
                          </button>
                        )
                      })}
                    </div>
                    {contextSettings.mode === 'auto' && (
                      <label className="block space-y-1 text-xs text-[var(--color-text-secondary)]">
                        <span>最大 token</span>
                        <input
                          type="number"
                          min={1}
                          step={500}
                          value={contextSettings.max_tokens || ''}
                          onChange={(e) => setContextSettings((current) => ({
                            ...current,
                            max_tokens: e.target.value === '' ? 0 : Math.max(1, Number(e.target.value) || 0),
                          }))}
                          className="h-8 w-full px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)]"
                        />
                      </label>
                    )}
                    {contextSettings.mode === 'custom' && (
                      <label className="block space-y-1 text-xs text-[var(--color-text-secondary)]">
                        <span>保留最近对话轮数</span>
                        <input
                          type="number"
                          min={1}
                          max={50}
                          value={contextSettings.recent_turns || ''}
                          onChange={(e) => setContextSettings((current) => ({
                            ...current,
                            recent_turns: e.target.value === '' ? 0 : Math.max(1, Number(e.target.value) || 0),
                          }))}
                          className="h-8 w-full px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)]"
                        />
                      </label>
                    )}
                  </div>

                  <div className="space-y-3 border-t border-[var(--color-border)] pt-3">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-[var(--color-text)]">RAG 检索</span>
                      <span className="text-[var(--color-text-secondary)]">控制检索与摘要数量</span>
                    </div>
                    <div className="grid grid-cols-5 gap-2">
                      {[
                        { value: 'auto', label: 'Auto' },
                        { value: 'low', label: '低' },
                        { value: 'medium', label: '中' },
                        { value: 'high', label: '高' },
                        { value: 'custom', label: '自定义' },
                      ].map((mode) => {
                        const active = ragRetrievalSettings.mode === mode.value
                        return (
                          <button
                            key={mode.value}
                            type="button"
                            onClick={() => setRagRetrievalSettings((current) => ({
                              ...current,
                              mode: mode.value as RagRetrievalMode,
                              knowledge_k: mode.value === 'low'
                                ? 4
                                : mode.value === 'medium'
                                  ? 6
                                  : mode.value === 'high'
                                    ? 10
                                    : current.knowledge_k,
                              note_k: mode.value === 'low'
                                ? 2
                                : mode.value === 'medium'
                                  ? 3
                                  : mode.value === 'high'
                                    ? 5
                                    : current.note_k,
                              summary_k: mode.value === 'low'
                                ? 2
                                : mode.value === 'medium'
                                  ? 3
                                  : mode.value === 'high'
                                    ? 5
                                    : current.summary_k,
                            }))}
                            className={`h-8 rounded-md border text-xs transition-colors ${
                              active
                                ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                                : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]'
                            }`}
                          >
                            {mode.label}
                          </button>
                        )
                      })}
                    </div>
                    {ragRetrievalSettings.mode === 'custom' && (
                      <div className="grid grid-cols-3 gap-2">
                        {[
                          { key: 'knowledge_k', label: '知识库', max: 20 },
                          { key: 'note_k', label: '笔记', max: 20 },
                          { key: 'summary_k', label: '摘要', max: 8 },
                        ].map((item) => (
                          <label key={item.key} className="block space-y-1 text-xs text-[var(--color-text-secondary)]">
                            <span>{item.label}</span>
                            <input
                              type="number"
                              min={1}
                              max={item.max}
                              value={ragRetrievalSettings[item.key as keyof RagRetrievalSettings] || ''}
                              onChange={(e) => setRagRetrievalSettings((current) => ({
                                ...current,
                                [item.key]: e.target.value === '' ? 0 : Math.max(1, Math.min(item.max, Number(e.target.value) || 0)),
                              }))}
                              className="h-8 w-full px-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-xs text-[var(--color-text)]"
                            />
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="flex gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('chat.input')}
              rows={1}
              className="flex-1 px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-placeholder)] resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            />
            <button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || loading}
              className="flex items-center justify-center w-10 h-10 rounded-lg bg-[var(--color-accent)] text-white hover:bg-blue-700 disabled:opacity-40 transition-colors shrink-0"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}


