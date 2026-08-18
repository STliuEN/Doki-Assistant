import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeftRight, Clipboard, Eraser, FilePlus2, Loader2, Play, Send } from 'lucide-react'
import { modelConfigApi } from '../api/modelConfig'
import { notesApi } from '../api/notes'
import { translateApi } from '../api/translate'
import { useSSE } from '../hooks/useSSE'
import type { ModelConfig } from '../types/api'
import { getAccessToken } from '../stores/useUserStore'

type TranslateMode = 'document' | 'dialogue'
type DialogueItem = {
  id: string
  source: string
  output: string
  status: 'running' | 'done' | 'error'
  error?: string
}

const TRANSLATE_MODEL_STORAGE_KEY = 'translate_selected_model_id'
const languageOptions = ['中文', '日语', '英语', '韩语', '法语', '德语', '西班牙语', '俄语', '阿拉伯语']

function modelLabel(config: ModelConfig): string {
  return [config.provider, config.model_name].filter(Boolean).join(' / ') || '未命名模型'
}

function getErrorMessage(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string; detail?: string } } })?.response?.data
  return data?.message || data?.detail || '请求没有正常返回'
}

export default function RealtimeTranslate() {
  const documentSSE = useSSE()
  const [mode, setMode] = useState<TranslateMode>('dialogue')
  const [languageA, setLanguageA] = useState('中文')
  const [languageB, setLanguageB] = useState('日语')
  const [documentInput, setDocumentInput] = useState('')
  const [documentOutput, setDocumentOutput] = useState('')
  const [dialogueInput, setDialogueInput] = useState('')
  const [dialogueItems, setDialogueItems] = useState<DialogueItem[]>([])
  const [selectedModelId, setSelectedModelId] = useState(() => localStorage.getItem(TRANSLATE_MODEL_STORAGE_KEY) || '')
  const [customInstruction, setCustomInstruction] = useState('')
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([])
  const [message, setMessage] = useState('')
  const documentOutputRef = useRef('')
  const rafRef = useRef<number | null>(null)
  const dialogueEndRef = useRef<HTMLDivElement>(null)

  const showMessage = (value: string) => {
    setMessage(value)
    window.setTimeout(() => setMessage(''), 5000)
  }

  const flushDocumentOutput = useCallback(() => {
    setDocumentOutput(documentOutputRef.current)
  }, [])

  useEffect(() => {
    modelConfigApi.list()
      .then((res) => setModelConfigs(res.data || []))
      .catch(() => showMessage('模型配置加载失败'))
  }, [])

  useEffect(() => {
    localStorage.setItem(TRANSLATE_MODEL_STORAGE_KEY, selectedModelId)
  }, [selectedModelId])

  useEffect(() => {
    dialogueEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [dialogueItems])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [])

  const requestBody = (text: string, fastMode: boolean) => ({
    language_a: languageA,
    language_b: languageB,
    text,
    fast_mode: fastMode,
    ...(customInstruction.trim() ? { custom_instruction: customInstruction.trim() } : {}),
    ...(selectedModelId ? { model_config_id: selectedModelId } : {}),
  })

  const handleDocumentTranslate = async () => {
    if (!documentInput.trim() || documentSSE.loading) return
    if (languageA === languageB) {
      showMessage('请选择两种不同的语言')
      return
    }

    documentOutputRef.current = ''
    setDocumentOutput('')
    await documentSSE.start(
      translateApi.dialogueStream,
      requestBody(documentInput, false),
      {
        onResponse: (content) => {
          documentOutputRef.current += content
          if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
              rafRef.current = null
              flushDocumentOutput()
            })
          }
        },
        onDone: () => {
          if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
          }
          flushDocumentOutput()
        },
        onError: (error) => showMessage(error),
      }
    )
  }

  const translateDialogueLine = async (id: string, text: string) => {
    const token = getAccessToken()
    try {
      const response = await fetch(translateApi.dialogueStream, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody(text, true)),
      })

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))
          if (data.type === 'response' && data.content) {
            setDialogueItems((prev) => prev.map((item) => (
              item.id === id ? { ...item, output: item.output + data.content } : item
            )))
          }
          if (data.type === 'error') {
            throw new Error(data.content || '翻译失败')
          }
        }
      }

      setDialogueItems((prev) => prev.map((item) => (
        item.id === id ? { ...item, status: 'done' } : item
      )))
    } catch (error) {
      setDialogueItems((prev) => prev.map((item) => (
        item.id === id ? { ...item, status: 'error', error: getErrorMessage(error) || String(error) } : item
      )))
    }
  }

  const handleSendDialogue = () => {
    const text = dialogueInput.trim()
    if (!text) return
    if (languageA === languageB) {
      showMessage('请选择两种不同的语言')
      return
    }

    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    setDialogueItems((prev) => [...prev, { id, source: text, output: '', status: 'running' }])
    setDialogueInput('')
    void translateDialogueLine(id, text)
  }

  const handleDialogueKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSendDialogue()
    }
  }

  const handleSwapLanguages = () => {
    setLanguageA(languageB)
    setLanguageB(languageA)
  }

  const handleClear = () => {
    if (mode === 'document') {
      setDocumentInput('')
      setDocumentOutput('')
      documentOutputRef.current = ''
    } else {
      setDialogueInput('')
      setDialogueItems([])
    }
  }

  const currentOutput = mode === 'document'
    ? documentOutput
    : dialogueItems.map((item) => item.output).join('\n')

  const handleCopy = async () => {
    if (!currentOutput.trim()) return
    try {
      await navigator.clipboard.writeText(currentOutput)
      showMessage('翻译结果已复制')
    } catch {
      showMessage('复制失败，请手动选择文本复制')
    }
  }

  const handleSaveNote = async () => {
    const source = mode === 'document'
      ? documentInput
      : dialogueItems.map((item) => `原文：${item.source}\n译文：${item.output}`).join('\n\n')
    if (!source.trim() || !currentOutput.trim()) {
      showMessage('需要先完成一次翻译')
      return
    }

    const selectedModel = modelConfigs.find((item) => item.id === selectedModelId)
    const modelName = selectedModel ? modelLabel(selectedModel) : '工程默认配置'
    const content = [
      `# 实时双语翻译：${languageA} / ${languageB}`,
      '',
      `- 语言：${languageA} / ${languageB}`,
      `- 模型：${modelName}`,
      `- 模式：${mode === 'document' ? '整篇翻译' : '实时对话'}`,
      '',
      '## 内容',
      '',
      source,
    ].join('\n')

    try {
      await notesApi.create({
        title: `实时翻译 ${languageA}-${languageB}`,
        content,
        category: '实时翻译',
        tags: ['实时翻译', languageA, languageB],
      })
      showMessage('已保存为笔记')
    } catch (error) {
      showMessage(`保存失败：${getErrorMessage(error)}`)
    }
  }

  return (
    <div className="h-full flex flex-col bg-[var(--color-bg)]">
      <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMode('dialogue')}
              className={`px-3 py-2 text-sm rounded-md border ${
                mode === 'dialogue'
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              实时对话
            </button>
            <button
              onClick={() => setMode('document')}
              className={`px-3 py-2 text-sm rounded-md border ${
                mode === 'document'
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              整篇翻译
            </button>
          </div>
          {message && <span className="text-sm text-[var(--color-accent)]">{message}</span>}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <select
            value={languageA}
            onChange={(event) => setLanguageA(event.target.value)}
            className="h-9 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
          >
            {languageOptions.map((language) => (
              <option key={language} value={language}>{language}</option>
            ))}
          </select>
          <button
            onClick={handleSwapLanguages}
            title="交换语言"
            className="h-9 w-9 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
          >
            <ArrowLeftRight size={16} />
          </button>
          <select
            value={languageB}
            onChange={(event) => setLanguageB(event.target.value)}
            className="h-9 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
          >
            {languageOptions.map((language) => (
              <option key={language} value={language}>{language}</option>
            ))}
          </select>
          <select
            value={selectedModelId}
            onChange={(event) => setSelectedModelId(event.target.value)}
            className="h-9 min-w-64 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
          >
            <option value="">工程默认配置</option>
            {modelConfigs.map((config) => (
              <option key={config.id} value={config.id}>
                {modelLabel(config)}
                {config.is_default ? '（默认）' : ''}
              </option>
            ))}
          </select>
          <input
            value={customInstruction}
            onChange={(event) => setCustomInstruction(event.target.value)}
            placeholder="额外要求，如：用鲁迅的语气"
            className="h-9 min-w-72 flex-1 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-placeholder)]"
          />
        </div>
      </div>

      {mode === 'document' ? (
        <div className="flex-1 min-h-0 grid grid-cols-2">
          <section className="min-h-0 flex flex-col border-r border-[var(--color-border)]">
            <div className="h-11 shrink-0 px-5 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
              <span className="text-sm font-medium text-[var(--color-text)]">输入</span>
              <span className="text-xs text-[var(--color-text-tertiary)]">{documentInput.length} 字符</span>
            </div>
            <textarea
              value={documentInput}
              onChange={(event) => setDocumentInput(event.target.value)}
              placeholder={`输入 ${languageA} 或 ${languageB}，整篇翻译会保持上下文一致`}
              className="flex-1 min-h-72 resize-none border-0 bg-[var(--color-card)] p-5 text-sm leading-7 text-[var(--color-text)] placeholder:text-[var(--color-text-placeholder)] focus:outline-none"
            />
          </section>

          <section className="min-h-0 flex flex-col">
            <div className="h-11 shrink-0 px-5 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
              <span className="text-sm font-medium text-[var(--color-text)]">翻译结果</span>
              {documentSSE.loading && <Loader2 size={16} className="animate-spin text-[var(--color-accent)]" />}
            </div>
            <div className="flex-1 min-h-72 overflow-y-auto bg-[var(--color-card)] p-5">
              {documentOutput ? (
                <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-[var(--color-text)]">{documentOutput}</pre>
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">
                  翻译结果会显示在这里
                </div>
              )}
            </div>
          </section>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col bg-[var(--color-card)]">
          <div className="h-11 shrink-0 grid grid-cols-2 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
            <div className="px-5 flex items-center border-r border-[var(--color-border)]">
              <span className="text-sm font-medium text-[var(--color-text)]">对话输入</span>
            </div>
            <div className="px-5 flex items-center">
              <span className="text-sm font-medium text-[var(--color-text)]">实时译文</span>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-5">
            {dialogueItems.length === 0 ? (
              <div className="h-full grid grid-cols-2 gap-6">
                <div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">
                  输入内容会显示在这里
                </div>
                <div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">
                  译文会逐句显示在这里
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {dialogueItems.map((item) => (
                  <div key={item.id} className="grid grid-cols-2 gap-6 items-stretch">
                    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-sm leading-6 text-[var(--color-text)] whitespace-pre-wrap break-words">
                      {item.source}
                    </div>
                    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-sm leading-6 text-[var(--color-text)] whitespace-pre-wrap break-words">
                      {item.output || (item.status === 'running' ? '翻译中...' : '')}
                      {item.status === 'running' && <Loader2 size={14} className="ml-2 inline animate-spin text-[var(--color-accent)]" />}
                      {item.status === 'error' && <span className="text-[var(--color-danger)]">{item.error || '翻译失败'}</span>}
                    </div>
                  </div>
                ))}
                <div ref={dialogueEndRef} />
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[var(--color-border)] p-4">
            <div className="flex gap-2">
              <textarea
                value={dialogueInput}
                onChange={(event) => setDialogueInput(event.target.value)}
                onKeyDown={handleDialogueKeyDown}
                placeholder="输入一句话，按 Enter 发送，Shift+Enter 换行"
                rows={2}
                className="flex-1 resize-none rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm leading-6 text-[var(--color-text)] placeholder:text-[var(--color-text-placeholder)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
              <button
                onClick={handleSendDialogue}
                disabled={!dialogueInput.trim()}
                className="w-10 rounded-md bg-[var(--color-accent)] text-white inline-flex items-center justify-center disabled:opacity-50"
                title="发送"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="shrink-0 border-t border-[var(--color-border)] bg-[var(--color-card)] px-6 py-3">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            onClick={handleClear}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
          >
            <Eraser size={16} />
            清空
          </button>
          <button
            onClick={handleCopy}
            disabled={!currentOutput.trim()}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
          >
            <Clipboard size={16} />
            复制
          </button>
          <button
            onClick={handleSaveNote}
            disabled={!currentOutput.trim()}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
          >
            <FilePlus2 size={16} />
            保存笔记
          </button>
          {mode === 'document' && (
            <button
              onClick={handleDocumentTranslate}
              disabled={!documentInput.trim() || documentSSE.loading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-[var(--color-accent)] text-white disabled:opacity-50"
            >
              {documentSSE.loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              开始翻译
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
