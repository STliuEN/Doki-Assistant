import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { knowledgeApi } from '../../api/knowledge'
import type { RagIndexConfig, RagQueryConfig, RagStatus } from '../../types/api'

const labels: Record<RagStatus['status'], string> = {
  uninitialized: '尚未建立索引', queued: '等待构建', building: '正在构建', ready: '检索已就绪', failed: '构建失败',
}
const inputClass = 'mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm'
const buttonClass = 'rounded border border-[var(--color-border)] px-3 py-2 text-sm disabled:opacity-50'

export default function RagSettings({ onStatus }: { onStatus: (value: RagStatus) => void }) {
  const [state, setState] = useState<RagStatus | null>(null)
  const [query, setQuery] = useState<RagQueryConfig | null>(null)
  const [index, setIndex] = useState<RagIndexConfig | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [unavailable, setUnavailable] = useState(false)
  const dirty = useRef({ query: false, index: false })
  const versions = useRef({ query: 0, index: 0 })
  const callback = useRef(onStatus)
  useEffect(() => { callback.current = onStatus }, [onStatus])

  const apply = useCallback((value: RagStatus) => {
    setState(value)
    setError('')
    if (!dirty.current.query) { setQuery(value.query_config); versions.current.query = value.query_revision }
    if (!dirty.current.index) { setIndex(value.index_config); versions.current.index = value.revision }
    callback.current(value)
  }, [])
  const applyRef = useRef(apply)
  useEffect(() => { applyRef.current = apply }, [apply])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const response = await knowledgeApi.ragStatus()
        if (!cancelled && response.data) applyRef.current(response.data)
      } catch (failure) {
        if (cancelled) return
        if ((failure as { response?: { status?: number } }).response?.status === 404) { setUnavailable(true); return }
        setError('暂时无法读取索引状态，正在重试')
      }
      if (!cancelled) timer = setTimeout(poll, 5000)
    }
    void poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  const save = async (kind: 'query' | 'index' | 'rebuild') => {
    if (!query || !index) return
    setBusy(true)
    try {
      const result = kind === 'query'
        ? await knowledgeApi.saveRagQuery(query, versions.current.query)
        : kind === 'index' ? await knowledgeApi.saveRagIndex(index, versions.current.index) : await knowledgeApi.rebuildRag()
      if (kind !== 'rebuild') dirty.current[kind] = false
      if (result.data) apply(result.data)
      toast.success(kind === 'query' ? '检索设置已保存' : '重建请求已登记，请等待索引就绪')
    } catch {
      setError('保存失败：请检查配置或重新载入已保存的设置后重试')
    } finally { setBusy(false) }
  }

  if (unavailable) return null
  if (!state || !query || !index) return <p role="status" className="mb-4 text-sm">{error || '正在读取索引状态…'}</p>
  const building = state.status === 'queued' || state.status === 'building'
  return (
    <section aria-label="检索设置" className="mb-5 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 text-[var(--color-text)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div role="status" data-testid="rag-status" data-status={error ? 'unknown' : state.status}>
          <p className="font-medium">{error ? '索引状态待确认' : labels[state.status]}</p>
          <p className="text-xs text-[var(--color-text-tertiary)]">
            {building ? '构建完成后恢复检索，可离开或刷新此页面。' : `知识 ${state.generations.knowledge?.chunks ?? 0} 段 · 笔记 ${state.generations.notes?.chunks ?? 0} 段`}
          </p>
        </div>
        <button className={buttonClass} disabled={busy || building} onClick={() => void save('rebuild')}>
          {state.status === 'failed' ? '重试构建' : '重建索引'}
        </button>
      </div>
      {state.status === 'failed' && <p role="alert" className="mb-3 text-sm text-[var(--color-danger)]">索引构建失败，请检查文档和模型后重试。</p>}
      {error && <p role="alert" className="mb-3 text-sm text-[var(--color-danger)]">{error}</p>}
      <fieldset disabled={busy} className="mb-4 border-b border-[var(--color-border)] pb-4">
        <legend className="mb-2 text-sm font-medium">检索参数</legend>
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          {([['bm25', '关键词检索'], ['hyde', '假设答案扩展'], ['notes', '包含笔记'], ['rerank', '结果重排']] as const).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={query[key]}
              onChange={e => { dirty.current.query = true; setQuery({ ...query, [key]: e.target.checked }) }} />{label}</label>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">返回条数<input aria-label="返回条数" className={inputClass} type="number" min={1} max={50} value={query.top_k}
            onChange={e => { dirty.current.query = true; setQuery({ ...query, top_k: Number(e.target.value) }) }} /></label>
          <label className="text-sm">扩展模型<input className={inputClass} value={query.hyde_model}
            onChange={e => { dirty.current.query = true; setQuery({ ...query, hyde_model: e.target.value }) }} /></label>
          <label className="text-sm">重排模型<select className={inputClass} value={query.reranker_model}
            onChange={e => { dirty.current.query = true; setQuery({ ...query, reranker_model: e.target.value }) }}>
            <option value="qwen3-reranker-4b">Qwen3 4B</option><option value="qwen3-reranker-0.6b">Qwen3 0.6B</option>
            <option value="bge-reranker-v2-m3">BGE v2 M3</option>
          </select></label>
        </div>
        <button className={`${buttonClass} mt-3`} onClick={() => void save('query')}>保存检索设置</button>
      </fieldset>
      <fieldset disabled={busy || building}>
        <legend className="mb-2 text-sm font-medium">文档切片</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">每段字符数<input aria-label="每段字符数" className={inputClass} type="number" min={128} max={8000} value={index.chunk_size}
            onChange={e => { dirty.current.index = true; setIndex({ ...index, chunk_size: Number(e.target.value) }) }} /></label>
          <label className="text-sm">相邻段落重叠字符数<input className={inputClass} type="number" min={0} max={Math.min(2000, index.chunk_size - 1)} value={index.chunk_overlap}
            onChange={e => { dirty.current.index = true; setIndex({ ...index, chunk_overlap: Number(e.target.value) }) }} /></label>
        </div>
        <button className={`${buttonClass} mt-3`} onClick={() => void save('index')}>保存切片并重建</button>
      </fieldset>
      <button className="mt-3 text-xs underline" disabled={busy} onClick={() => {
        dirty.current = { query: false, index: false }; apply(state)
      }}>重新载入已保存的设置</button>
    </section>
  )
}
