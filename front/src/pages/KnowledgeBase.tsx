import { useCallback, useEffect, useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Upload, FileText, Trash2, Loader2, CheckCircle2, AlertCircle, RefreshCw, Database, RotateCcw, Download, SlidersHorizontal } from 'lucide-react'
import { knowledgeApi } from '../api/knowledge'
import { useSSE } from '../hooks/useSSE'
import type { EmbeddingConfig, KnowledgeDocument, KnowledgeSSEMessage, LocalRerankerModel, RerankerConfig } from '../types/api'
import EmptyState from '../components/common/EmptyState'
import ConfirmDialog from '../components/common/ConfirmDialog'
import DocumentDetailDrawer from '../components/knowledge/DocumentDetailDrawer'
import { getAccessToken } from '../stores/useUserStore'

interface UploadFile {
  file: File
  documentId?: string
  progress: number
  status: 'pending' | 'queued' | 'uploading' | 'success' | 'fail'
  stage?: string
  error?: string
  chunkCount?: number
}

const DEFAULT_OLLAMA_BASE_URL = 'http://localhost:11434'

const progressByEvent: Partial<Record<KnowledgeSSEMessage['event_type'], number>> = {
  queued: 10,
  processing: 30,
  slicing_completed: 65,
  writing: 85,
  completed: 100,
  error: 100,
}

export default function KnowledgeBase() {
  const { t } = useTranslation()
  const { start: startSSE } = useSSE()
  const [docs, setDocs] = useState<KnowledgeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [uploadFiles, setUploadFiles] = useState<UploadFile[]>([])
  const [uploadTotal, setUploadTotal] = useState(0)
  const [uploadDone, setUploadDone] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const [showClean, setShowClean] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocument | null>(null)
  const [detailFilename, setDetailFilename] = useState<string | null>(null)
  const [embedding, setEmbedding] = useState<EmbeddingConfig | null>(null)
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState(DEFAULT_OLLAMA_BASE_URL)
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([])
  const [loadingEmbeddingModels, setLoadingEmbeddingModels] = useState(false)
  const [switchingEmbedding, setSwitchingEmbedding] = useState(false)
  const [reranker, setReranker] = useState<RerankerConfig | null>(null)
  const [rerankerModels, setRerankerModels] = useState<LocalRerankerModel[]>([])
  const [rerankerModelPath, setRerankerModelPath] = useState('')
  const [rerankerModelName, setRerankerModelName] = useState('')
  const [rerankerMaxLength, setRerankerMaxLength] = useState(8192)
  const [rerankerBatchSize, setRerankerBatchSize] = useState(1)
  const [rerankerDtype, setRerankerDtype] = useState('auto')
  const [loadingRerankerModels, setLoadingRerankerModels] = useState(false)
  const [switchingReranker, setSwitchingReranker] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const rerankerModelPathRef = useRef('')

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await knowledgeApi.list()
      const documents = (res.data as { documents: KnowledgeDocument[] } | undefined)?.documents || []
      setDocs(documents)
    } catch {
      toast.error('加载文档列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadEmbedding = useCallback(async () => {
    try {
      const res = await knowledgeApi.currentEmbedding()
      if (res.data) {
        setEmbedding(res.data)
        setEmbeddingModel(res.data.model_name)
        setEmbeddingBaseUrl(res.data.base_url || DEFAULT_OLLAMA_BASE_URL)
      }
    } catch {
      toast.error('加载嵌入模型配置失败')
    }
  }, [])

  const applyRerankerConfig = useCallback((config: RerankerConfig) => {
    setReranker(config)
    rerankerModelPathRef.current = config.model_path
    setRerankerModelPath(config.model_path)
    setRerankerModelName(config.model_name)
    setRerankerMaxLength(config.max_length || 8192)
    setRerankerBatchSize(config.batch_size || 1)
    setRerankerDtype(config.torch_dtype || 'auto')
  }, [])

  const loadRerankerModels = useCallback(async (showMessage = true, selectedPath?: string) => {
    setLoadingRerankerModels(true)
    try {
      const res = await knowledgeApi.listLocalRerankerModels()
      const models = res.data?.models || []
      setRerankerModels(models)
      const activePath = selectedPath ?? rerankerModelPathRef.current
      if (!activePath && models.length > 0) {
        rerankerModelPathRef.current = models[0].model_path
        setRerankerModelPath(models[0].model_path)
        setRerankerModelName(models[0].model_name)
      }
      if (showMessage) toast.success(`已读取 ${models.length} 个本地重排序模型`)
    } catch {
      toast.error('读取本地重排序模型失败')
    } finally {
      setLoadingRerankerModels(false)
    }
  }, [])

  const loadReranker = useCallback(async () => {
    try {
      const res = await knowledgeApi.currentReranker()
      if (res.data) {
        applyRerankerConfig(res.data)
        await loadRerankerModels(false, res.data.model_path)
      }
    } catch {
      toast.error('加载重排序模型配置失败')
    }
  }, [applyRerankerConfig, loadRerankerModels])

  useEffect(() => {
    loadDocs()
    loadEmbedding()
    loadReranker()
  }, [loadDocs, loadEmbedding, loadReranker])

  const updateUploadFile = (data: KnowledgeSSEMessage, patch: Partial<UploadFile>) => {
    setUploadFiles((prev) =>
      prev.map((uf) =>
        uf.file.name === data.filename || uf.documentId === data.document_id
          ? {
              ...uf,
              documentId: data.document_id || uf.documentId,
              progress: data.progress ?? progressByEvent[data.event_type] ?? uf.progress,
              stage: data.message || data.step || uf.stage,
              ...patch,
            }
          : uf
      )
    )
  }

  const handleFilesSelected = (files: FileList) => {
    const newFiles: UploadFile[] = Array.from(files).map((f) => ({ file: f, progress: 0, status: 'pending' }))
    setUploadFiles(newFiles)
    setUploadTotal(newFiles.length)
    setUploadDone(0)

    const formData = new FormData()
    newFiles.forEach((f) => formData.append('files', f.file))

    startSSE(
      '/knowledge/add/multiple/stream',
      formData,
      {
        onKnowledgeProgress: (data: KnowledgeSSEMessage) => {
          if (data.event_type === 'queued') {
            updateUploadFile(data, { status: 'queued' })
          } else if (data.event_type === 'processing' || data.event_type === 'slicing_completed' || data.event_type === 'writing') {
            updateUploadFile(data, { status: 'uploading', chunkCount: data.chunk_count })
          } else if (data.event_type === 'completed') {
            updateUploadFile(data, { progress: 100, status: 'success', chunkCount: data.chunk_count })
            setUploadDone((c) => c + 1)
          } else if (data.event_type === 'error') {
            updateUploadFile(data, { status: 'fail', error: data.error_message || data.message || '处理失败' })
            setUploadDone((c) => c + 1)
          } else if (data.event_type === 'finish') {
            loadDocs()
          }
        },
        onError: () => {
          setUploadFiles((prev) =>
            prev.map((uf) =>
              uf.status === 'uploading' ? { ...uf, status: 'fail' as const } : uf
            )
          )
        },
      }
    )
  }

  const loadEmbeddingModels = async (showMessage = true) => {
    const url = (embeddingBaseUrl || DEFAULT_OLLAMA_BASE_URL).trim()
    setLoadingEmbeddingModels(true)
    try {
      const res = await knowledgeApi.listEmbeddingOllamaModels(url)
      const data = res.data
      const models = data?.models || []
      setEmbeddingModels(models)
      if (data?.base_url) setEmbeddingBaseUrl(data.base_url)
      if (!embeddingModel && models.length > 0) setEmbeddingModel(models[0])
      if (showMessage) {
        toast[data?.ok ? 'success' : 'error'](data?.ok ? `已读取 ${models.length} 个嵌入模型` : data?.error || '读取嵌入模型失败')
      }
    } catch {
      toast.error('读取嵌入模型失败')
    } finally {
      setLoadingEmbeddingModels(false)
    }
  }

  const handleSwitchEmbedding = async () => {
    if (!embeddingModel.trim()) {
      toast.error('请选择嵌入模型')
      return
    }
    if (!window.confirm('切换嵌入模型会重建当前账号的知识库和笔记索引，确认继续吗？')) return

    setSwitchingEmbedding(true)
    try {
      const res = await knowledgeApi.switchEmbedding({
        model_name: embeddingModel.trim(),
        base_url: embeddingBaseUrl.trim() || DEFAULT_OLLAMA_BASE_URL,
        provider: 'ollama',
        model_type: 'ollama',
      })
      setEmbedding(res.data.embedding)
      await loadDocs()
      toast.success(`索引已重建：知识库 ${res.data.knowledge_success}/${res.data.knowledge_total}，笔记 ${res.data.note_count}`)
    } catch {
      toast.error('切换嵌入模型失败')
    } finally {
      setSwitchingEmbedding(false)
    }
  }

  const handleRerankerPathChange = (path: string) => {
    rerankerModelPathRef.current = path
    setRerankerModelPath(path)
    const selected = rerankerModels.find((model) => model.model_path === path)
    if (selected) setRerankerModelName(selected.model_name)
  }

  const handleSwitchReranker = async () => {
    if (!rerankerModelPath.trim()) {
      toast.error('请选择重排序模型')
      return
    }
    setSwitchingReranker(true)
    try {
      const payload: RerankerConfig = {
        provider: 'local',
        model_name: rerankerModelName.trim() || rerankerModelPath.trim(),
        model_path: rerankerModelPath.trim(),
        revision: reranker?.revision || 'master',
        device: reranker?.device || 'auto',
        max_length: rerankerMaxLength || 8192,
        batch_size: rerankerBatchSize || 1,
        torch_dtype: rerankerDtype || 'auto',
        min_weight_mb: reranker?.min_weight_mb || 50,
        trust_remote_code: reranker?.trust_remote_code || false,
      }
      const res = await knowledgeApi.switchReranker(payload)
      applyRerankerConfig(res.data)
      toast.success('重排序模型已切换')
    } catch {
      toast.error('切换重排序模型失败')
    } finally {
      setSwitchingReranker(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await knowledgeApi.deleteByFilename(deleteTarget.filename)
      setDocs((prev) => prev.filter((d) => d.id !== deleteTarget.id))
    } catch {
      toast.error('删除文档失败')
    }
    setDeleteTarget(null)
  }

  const handleDownloadSource = async (doc: KnowledgeDocument) => {
    try {
      const token = getAccessToken()
      const response = await fetch(knowledgeApi.sourceUrl(doc.filename), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = doc.original_filename || doc.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('下载源文件失败')
    }
  }

  const handleCleanAll = async () => {
    try {
      await knowledgeApi.cleanAll()
      setDocs([])
    } catch {
      toast.error('清空知识库失败')
    }
    setShowClean(false)
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="max-w-4xl mx-auto py-8 px-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-heading text-xl font-semibold text-[var(--color-text)]">{t('knowledge.title')}</h1>
        {docs.length > 0 && (
          <button
            onClick={() => setShowClean(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)] transition-colors"
          >
            <Trash2 size={14} />
            {t('knowledge.cleanAll')}
          </button>
        )}
      </div>

      <div className="mb-5 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Database size={16} className="text-[var(--color-accent)] shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--color-text)]">Embedding</p>
              <p className="text-xs text-[var(--color-text-tertiary)] truncate">
                {embedding?.model_name || '未选择'}{embedding?.base_url ? ` · ${embedding.base_url}` : ''}
              </p>
            </div>
          </div>
          <button
            onClick={handleSwitchEmbedding}
            disabled={switchingEmbedding}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md bg-[var(--color-accent)] text-white disabled:opacity-50"
          >
            <RotateCcw size={15} className={switchingEmbedding ? 'animate-spin' : ''} />
            {switchingEmbedding ? '重建中' : '切换并重建'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr_auto] gap-3">
          <input
            value={embeddingBaseUrl}
            onChange={(e) => setEmbeddingBaseUrl(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
            placeholder={DEFAULT_OLLAMA_BASE_URL}
          />
          <select
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
          >
            <option value={embeddingModel}>{embeddingModel || '选择嵌入模型'}</option>
            {embeddingModels.filter((m) => m !== embeddingModel).map((model) => (
              <option key={model} value={model}>{model}</option>
            ))}
          </select>
          <button
            onClick={() => loadEmbeddingModels(true)}
            disabled={loadingEmbeddingModels}
            className="inline-flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
          >
            <RefreshCw size={15} className={loadingEmbeddingModels ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </div>

      <div className="mb-5 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <SlidersHorizontal size={16} className="text-[var(--color-accent)] shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--color-text)]">Reranker</p>
              <p className="text-xs text-[var(--color-text-tertiary)] truncate">
                {reranker?.model_name || '未选择'}{reranker?.model_path ? ` · ${reranker.model_path}` : ''}
              </p>
            </div>
          </div>
          <button
            onClick={handleSwitchReranker}
            disabled={switchingReranker}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md bg-[var(--color-accent)] text-white disabled:opacity-50"
          >
            <RotateCcw size={15} className={switchingReranker ? 'animate-spin' : ''} />
            {switchingReranker ? '切换中' : '切换'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[1.3fr_1fr_auto] gap-3">
          <select
            value={rerankerModelPath}
            onChange={(e) => handleRerankerPathChange(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
          >
            <option value={rerankerModelPath}>{rerankerModelPath || '选择本地重排序模型'}</option>
            {rerankerModels.filter((model) => model.model_path !== rerankerModelPath).map((model) => (
              <option key={model.model_path} value={model.model_path}>{model.label} · {model.model_path}</option>
            ))}
          </select>
          <input
            value={rerankerModelName}
            onChange={(e) => setRerankerModelName(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
            placeholder="Qwen/Qwen3-Reranker-4B"
          />
          <button
            onClick={() => loadRerankerModels(true)}
            disabled={loadingRerankerModels}
            className="inline-flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
          >
            <RefreshCw size={15} className={loadingRerankerModels ? 'animate-spin' : ''} />
            扫描
          </button>
        </div>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="text-xs text-[var(--color-text-tertiary)]">
            长度
            <input
              type="number"
              min={512}
              step={512}
              value={rerankerMaxLength}
              onChange={(e) => setRerankerMaxLength(Number(e.target.value))}
              className="mt-1 w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
            />
          </label>
          <label className="text-xs text-[var(--color-text-tertiary)]">
            批次
            <input
              type="number"
              min={1}
              value={rerankerBatchSize}
              onChange={(e) => setRerankerBatchSize(Number(e.target.value))}
              className="mt-1 w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
            />
          </label>
          <label className="text-xs text-[var(--color-text-tertiary)]">
            精度
            <select
              value={rerankerDtype}
              onChange={(e) => setRerankerDtype(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
            >
              <option value="auto">auto</option>
              <option value="float16">float16</option>
              <option value="bfloat16">bfloat16</option>
              <option value="float32">float32</option>
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-[var(--color-text-tertiary)]">切换重排序模型不会重建知识库索引。</p>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-lg p-10 text-center transition-colors ${
          dragOver ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)]' : 'border-[var(--color-border)] hover:border-[var(--color-text-tertiary)]'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.docx,.pptx"
          className="hidden"
          onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
        />
        <Upload size={24} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
        <p className="text-sm text-[var(--color-text-secondary)] mb-1">{t('knowledge.dragDrop')}</p>
        <p className="text-xs text-[var(--color-text-tertiary)] mb-4">{t('knowledge.fileTypes')}</p>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="px-4 py-2 text-sm rounded-md bg-[var(--color-accent)] text-white hover:bg-blue-700 transition-colors"
        >
          {t('knowledge.upload')}
        </button>
      </div>

      {uploadFiles.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploadFiles.map((uf, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)]">
              {uf.status === 'success' ? (
                <CheckCircle2 size={16} className="text-[var(--color-success)] shrink-0" />
              ) : uf.status === 'fail' ? (
                <AlertCircle size={16} className="text-[var(--color-danger)] shrink-0" />
              ) : (
                <Loader2 size={16} className="animate-spin text-[var(--color-accent)] shrink-0" />
              )}
              <span className="text-sm text-[var(--color-text)] flex-1 truncate">{uf.file.name}</span>
              <span className="text-xs text-[var(--color-text-tertiary)]">{formatSize(uf.file.size)}</span>
              <div className="w-32">
                <div className="h-1.5 rounded-full bg-[var(--color-bg-tertiary)] overflow-hidden">
                  <div className="h-full bg-[var(--color-accent)] rounded-full transition-all" style={{ width: `${uf.progress}%` }} />
                </div>
                <p className="mt-1 text-[10px] text-[var(--color-text-tertiary)] truncate">{uf.error || uf.stage || uf.status}</p>
              </div>
            </div>
          ))}
          {uploadDone === uploadTotal && uploadDone > 0 && (
            <p className="text-xs text-[var(--color-success)] text-center">{t('knowledge.success')}</p>
          )}
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-sm font-medium text-[var(--color-text)] mb-4">{t('knowledge.title')} ({docs.length})</h2>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-[var(--color-bg-tertiary)] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <EmptyState icon={<FileText size={48} />} message={t('knowledge.empty')} />
        ) : (
          <div className="space-y-2">
            {docs.map((doc) => (
              <div
                key={doc.id}
                onClick={() => setDetailFilename(doc.filename)}
                className="flex items-center justify-between px-4 py-3 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] hover:border-[var(--color-accent)] cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <FileText size={16} className="text-[var(--color-text-tertiary)] shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm text-[var(--color-text)] truncate">{doc.filename}</p>
                    <p className="text-xs text-[var(--color-text-tertiary)]">
                      {doc.chunk_count} chunks | {doc.status || 'indexed'} | {formatDate(doc.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDownloadSource(doc) }}
                    className="p-1.5 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] hover:bg-[var(--color-accent-bg)] transition-colors"
                  >
                    <Download size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(doc) }}
                    className="p-1.5 rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)] transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog open={showClean} onOpenChange={setShowClean} title={t('knowledge.cleanAll')} message={t('knowledge.cleanConfirm')} variant="danger" confirmText={t('knowledge.cleanAll')} onConfirm={handleCleanAll} />
      <ConfirmDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)} title={t('common.confirm')} message={t('knowledge.deleteConfirm')} variant="danger" confirmText={t('note.delete')} onConfirm={handleDelete} />
      <DocumentDetailDrawer filename={detailFilename} onClose={() => setDetailFilename(null)} />
    </div>
  )
}
