import { useEffect, useMemo, useState } from 'react'
import { Check, Pencil, Plus, RefreshCw, Save, Trash2, X, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { modelConfigApi } from '../api/modelConfig'
import type { ModelConfig, ModelConfigPayload, ModelType } from '../types/api'

type EditableModelType = Exclude<ModelType, 'default'>
const DEFAULT_OLLAMA_BASE_URL = 'http://localhost:11434'

const emptyForm: ModelConfigPayload = {
  model_type: 'openai_compatible',
  provider: '',
  model_name: '',
  base_url: '',
  api_key: '',
  is_default: false,
  is_active: true,
}

const modelTypeLabels: Record<ModelType, string> = {
  openai_compatible: '通用',
  ollama: 'Ollama 本地',
  default: '默认配置',
}

function normalizeForm(form: ModelConfigPayload): ModelConfigPayload {
  const baseUrl = form.base_url.trim()
  const isOllama = form.model_type === 'ollama'
  return {
    ...form,
    provider: isOllama ? 'ollama' : form.provider.trim(),
    model_name: form.model_name.trim(),
    base_url: isOllama ? baseUrl || DEFAULT_OLLAMA_BASE_URL : baseUrl,
    api_key: isOllama ? '' : form.api_key?.trim() || '',
  }
}

function getErrorMessage(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || '请求没有正常返回'
}

function modelToastLabel(config: Pick<ModelConfigPayload, 'provider' | 'model_name'>) {
  return [config.provider, config.model_name].filter(Boolean).join(' / ') || '当前模型'
}

function formatTestToast(status: '连接成功' | '连接失败', label: string, detail?: string) {
  return `${status}：${label}${detail ? `（${detail}）` : ''}`
}

export default function ModelSettings() {
  const [configs, setConfigs] = useState<ModelConfig[]>([])
  const [systemDefaultConfig, setSystemDefaultConfig] = useState<ModelConfig | null>(null)
  const [form, setForm] = useState<ModelConfigPayload>(emptyForm)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [loadingOllamaModels, setLoadingOllamaModels] = useState(false)
  const [message, setMessage] = useState('')

  const tableConfigs = useMemo(() => (
    systemDefaultConfig ? [systemDefaultConfig, ...configs] : configs
  ), [configs, systemDefaultConfig])

  const showMessage = (value: string) => {
    setMessage(value)
    window.setTimeout(() => setMessage(''), 6000)
  }

  const loadConfigs = async () => {
    const [systemRes, listRes] = await Promise.all([
      modelConfigApi.systemDefault(),
      modelConfigApi.list(),
    ])
    setSystemDefaultConfig(systemRes.data || null)
    setConfigs(listRes.data || [])
  }

  useEffect(() => {
    setLoading(true)
    loadConfigs()
      .catch(() => showMessage('模型配置加载失败'))
      .finally(() => setLoading(false))
  }, [])

  const resetForm = () => {
    setForm(emptyForm)
    setEditingId(null)
  }

  const loadOllamaModels = async (baseUrl?: string, showEmptyMessage = true) => {
    const url = (baseUrl || form.base_url || DEFAULT_OLLAMA_BASE_URL).trim()
    setLoadingOllamaModels(true)
    try {
      const res = await modelConfigApi.listOllamaModels(url)
      const data = res.data
      const models = data?.models || []
      setOllamaModels(models)
      if (data?.ok) {
        if (models.length > 0) {
          setForm((prev) => (
            prev.model_type === 'ollama' && !prev.model_name
              ? { ...prev, base_url: data.base_url || url, model_name: models[0] }
              : { ...prev, base_url: data.base_url || prev.base_url }
          ))
        }
        if (models.length === 0 && showEmptyMessage) {
          showMessage('Ollama 已连接，但没有读取到本地模型')
        } else if (showEmptyMessage) {
          showMessage(`已读取 ${models.length} 个 Ollama 模型`)
        }
      } else {
        showMessage(`读取 Ollama 模型失败：${data?.error || '未知错误'}`)
      }
    } catch (err) {
      showMessage(`读取 Ollama 模型失败：${getErrorMessage(err)}`)
    } finally {
      setLoadingOllamaModels(false)
    }
  }

  const handleModelTypeChange = (modelType: EditableModelType) => {
    if (modelType === 'ollama') {
      const baseUrl = DEFAULT_OLLAMA_BASE_URL
      setForm((prev) => ({
        ...prev,
        model_type: modelType,
        provider: 'ollama',
        base_url: baseUrl,
        api_key: '',
        model_name: prev.model_type === 'ollama' ? prev.model_name : '',
      }))
      loadOllamaModels(baseUrl, false)
      return
    }

    setForm((prev) => ({
      ...prev,
      model_type: modelType,
      provider: prev.provider === 'ollama' ? '' : prev.provider,
      model_name: prev.model_type === 'ollama' ? '' : prev.model_name,
      api_key: '',
    }))
  }

  const handleEdit = (config: ModelConfig) => {
    if (config.model_type === 'default') {
      showMessage('工程默认配置来自系统环境变量，不能在这里编辑')
      return
    }
    setEditingId(config.id)
    setForm({
      model_type: config.model_type,
      provider: config.provider,
      model_name: config.model_name,
      base_url: config.base_url,
      api_key: '',
      is_default: config.is_default,
      is_active: config.is_active,
    })
    if (config.model_type === 'ollama') {
      loadOllamaModels(config.base_url || DEFAULT_OLLAMA_BASE_URL, false)
    }
  }

  const validateForm = (payload: ModelConfigPayload) => {
    if (!payload.model_name) return '请填写模型名称'
    if (!payload.base_url) return '请填写模型 Base URL'
    if (payload.model_type === 'openai_compatible' && !editingId && !payload.api_key) return '通用模型需要填写 API SK'
    return ''
  }

  const handleSubmit = async () => {
    const payload = normalizeForm(form)
    const error = validateForm(payload)
    if (error) {
      showMessage(error)
      return
    }

    setLoading(true)
    try {
      if (editingId) {
        await modelConfigApi.update(editingId, payload)
        showMessage('模型配置已更新')
      } else {
        await modelConfigApi.create(payload)
        showMessage('模型配置已添加')
      }
      resetForm()
      await loadConfigs()
    } catch (err) {
      showMessage(`保存失败：${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (config: ModelConfig) => {
    if (config.model_type === 'default') {
      showMessage('工程默认配置不能删除')
      return
    }
    const label = config.provider || config.model_name || '这个模型配置'
    if (!window.confirm(`确定删除 ${label} 吗？`)) return

    setLoading(true)
    try {
      await modelConfigApi.delete(config.id)
      await loadConfigs()
      if (editingId === config.id) resetForm()
      showMessage('模型配置已删除')
    } catch (err) {
      showMessage(`删除失败：${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSetDefault = async (config: ModelConfig) => {
    if (config.model_type === 'default') {
      showMessage('工程默认配置固定在第一项，不能在这里设置')
      return
    }
    setLoading(true)
    try {
      await modelConfigApi.setDefault(config.id)
      await loadConfigs()
      showMessage('默认模型已更新')
    } catch (err) {
      showMessage(`设置默认模型失败：${getErrorMessage(err)}`)
    } finally {
      setLoading(false)
    }
  }

  const showTestResult = (data: { ok: boolean; result: string; error: string } | undefined, label: string) => {
    if (data?.ok) {
      toast.success(formatTestToast('连接成功', label, data.result || 'ok'))
    } else {
      toast.error(formatTestToast('连接失败', label, data?.error || '未知错误'))
    }
  }

  const handleTestForm = async () => {
    const payload = normalizeForm(form)
    const error = validateForm(payload)
    if (error) {
      showMessage(error)
      return
    }

    setTestingId('form')
    try {
      const res = await modelConfigApi.test(payload)
      showTestResult(res.data, modelToastLabel(payload))
    } catch (err) {
      toast.error(formatTestToast('连接失败', modelToastLabel(payload), getErrorMessage(err)))
    } finally {
      setTestingId(null)
    }
  }

  const handleTestSaved = async (config: ModelConfig) => {
    setTestingId(config.id)
    try {
      const res = config.model_type === 'default'
        ? await modelConfigApi.testSystemDefault()
        : await modelConfigApi.testSaved(config.id)
      showTestResult(res.data, modelToastLabel(config))
    } catch (err) {
      toast.error(formatTestToast('连接失败', modelToastLabel(config), getErrorMessage(err)))
    } finally {
      setTestingId(null)
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="font-heading text-xl font-semibold text-[var(--color-text)]">模型选择</h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">为当前账号添加 AI 对话可用的模型配置。</p>
          </div>
          {message && <span className="text-sm text-[var(--color-accent)] text-right max-w-xl">{message}</span>}
        </div>

        <div className="border border-[var(--color-border)] rounded-lg bg-[var(--color-card)] p-4">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">模型类型</span>
              <select
                value={form.model_type}
                onChange={(e) => handleModelTypeChange(e.target.value as EditableModelType)}
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              >
                <option value="openai_compatible">通用</option>
                <option value="ollama">Ollama 本地</option>
              </select>
            </label>
            {form.model_type === 'ollama' ? (
              <>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-xs text-[var(--color-text-secondary)]">Ollama 地址</span>
                  <input
                    value={form.base_url}
                    onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                    placeholder={DEFAULT_OLLAMA_BASE_URL}
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-xs text-[var(--color-text-secondary)]">本地模型</span>
                  <select
                    value={form.model_name}
                    onChange={(e) => setForm((prev) => ({ ...prev, model_name: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  >
                    <option value="">请选择 Ollama 模型</option>
                    {ollamaModels.map((model) => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">供应商</span>
                  <input
                    value={form.provider}
                    onChange={(e) => setForm((prev) => ({ ...prev, provider: e.target.value }))}
                    placeholder="DeepSeek / OpenAI / Ollama"
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">模型名称</span>
                  <input
                    value={form.model_name}
                    onChange={(e) => setForm((prev) => ({ ...prev, model_name: e.target.value }))}
                    placeholder="gpt-4o-mini / qwen3:7b"
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">模型 Base URL</span>
                  <input
                    value={form.base_url}
                    onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                    placeholder="https://api.example.com/v1"
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">API SK</span>
                  <input
                    value={form.api_key || ''}
                    onChange={(e) => setForm((prev) => ({ ...prev, api_key: e.target.value }))}
                    placeholder="sk-..."
                    type="password"
                    className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
                  />
                </label>
              </>
            )}
          </div>
          <div className="mt-4 flex items-center justify-between">
            <label className="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
              <input
                type="checkbox"
                checked={!!form.is_default}
                onChange={(e) => setForm((prev) => ({ ...prev, is_default: e.target.checked }))}
              />
              设为默认
            </label>
            <div className="flex gap-2">
              {form.model_type === 'ollama' && (
                <button
                  onClick={() => loadOllamaModels(form.base_url, true)}
                  disabled={loadingOllamaModels || loading}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
                >
                  <RefreshCw size={16} className={loadingOllamaModels ? 'animate-spin' : ''} />
                  {loadingOllamaModels ? '读取中' : '刷新模型'}
                </button>
              )}
              <button
                onClick={handleTestForm}
                disabled={testingId === 'form' || loading}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
              >
                <Zap size={16} />
                {testingId === 'form' ? '测试中' : '测试连接'}
              </button>
              {editingId && (
                <button
                  onClick={resetForm}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
                >
                  <X size={16} />
                  取消
                </button>
              )}
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md bg-[var(--color-accent)] text-white disabled:opacity-50"
              >
                {editingId ? <Save size={16} /> : <Plus size={16} />}
                {editingId ? '保存修改' : '添加模型'}
              </button>
            </div>
          </div>
        </div>

        <div className="border border-[var(--color-border)] rounded-lg bg-[var(--color-card)] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]">
              <tr>
                <th className="text-left font-medium px-4 py-3">模型类型</th>
                <th className="text-left font-medium px-4 py-3">供应商</th>
                <th className="text-left font-medium px-4 py-3">模型名称</th>
                <th className="text-left font-medium px-4 py-3">模型 Base URL</th>
                <th className="text-left font-medium px-4 py-3">API SK</th>
                <th className="text-right font-medium px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {tableConfigs.map((config) => (
                <tr key={config.id} className="border-t border-[var(--color-border)]">
                  <td className="px-4 py-3 text-[var(--color-text)]">
                    {modelTypeLabels[config.model_type]}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.provider || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.model_name || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)] max-w-xs truncate">{config.base_url || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.api_key_masked || '-'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <span className="inline-flex w-20 justify-center">
                        {config.is_default && (
                          <span className="rounded-md bg-[var(--color-accent-bg)] px-2 py-0.5 text-xs font-medium text-[var(--color-accent)]">
                            {config.model_type === 'default' ? '工程默认' : '默认'}
                          </span>
                        )}
                      </span>
                      <button title="测试连接" onClick={() => handleTestSaved(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50" disabled={testingId === config.id}>
                        <Zap size={16} />
                      </button>
                      {config.model_type !== 'default' && (
                        <>
                          <button title="设为默认" onClick={() => handleSetDefault(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]">
                            <Check size={16} />
                          </button>
                          <button title="编辑" onClick={() => handleEdit(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]">
                            <Pencil size={16} />
                          </button>
                          <button title="删除" onClick={() => handleDelete(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-danger)]">
                            <Trash2 size={16} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {tableConfigs.length === 0 && (
                <tr>
                  <td className="px-4 py-8 text-center text-[var(--color-text-tertiary)]" colSpan={6}>
                    暂无模型配置。AI 对话页仍可使用第一项“默认配置”。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
