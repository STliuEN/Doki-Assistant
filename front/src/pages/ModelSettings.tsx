import { useEffect, useMemo, useState } from 'react'
import { Check, Pencil, Plus, Save, Trash2, X, Zap } from 'lucide-react'
import { modelConfigApi } from '../api/modelConfig'
import type { ModelConfig, ModelConfigPayload, ModelType } from '../types/api'

type EditableModelType = Exclude<ModelType, 'default'>

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
  return {
    ...form,
    provider: form.provider.trim(),
    model_name: form.model_name.trim(),
    base_url: baseUrl,
    api_key: form.api_key?.trim() || '',
  }
}

function getErrorMessage(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string; detail?: string } } })?.response?.data
  return data?.message || data?.detail || '请求没有正常返回'
}

export default function ModelSettings() {
  const [configs, setConfigs] = useState<ModelConfig[]>([])
  const [form, setForm] = useState<ModelConfigPayload>(emptyForm)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  const sortedConfigs = useMemo(
    () => [...configs].sort((a, b) => Number(b.is_default) - Number(a.is_default)),
    [configs]
  )

  const showMessage = (value: string) => {
    setMessage(value)
    window.setTimeout(() => setMessage(''), 6000)
  }

  const loadConfigs = async () => {
    const res = await modelConfigApi.list()
    setConfigs(res.data || [])
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

  const handleEdit = (config: ModelConfig) => {
    if (config.model_type === 'default') {
      showMessage('默认配置来自系统环境变量，不能在这里编辑')
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
      showMessage('默认配置不能删除')
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

  const showTestResult = (data?: { ok: boolean; result: string; error: string }) => {
    if (data?.ok) {
      showMessage(`连接成功：${data.result || 'ok'}`)
    } else {
      showMessage(`连接失败：${data?.error || '未知错误'}`)
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
      showTestResult(res.data)
    } catch (err) {
      showMessage(`连接失败：${getErrorMessage(err)}`)
    } finally {
      setTestingId(null)
    }
  }

  const handleTestSaved = async (config: ModelConfig) => {
    setTestingId(config.id)
    try {
      const res = await modelConfigApi.testSaved(config.id)
      showTestResult(res.data)
    } catch (err) {
      showMessage(`连接失败：${getErrorMessage(err)}`)
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
                onChange={(e) => setForm((prev) => ({ ...prev, model_type: e.target.value as EditableModelType }))}
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              >
                <option value="openai_compatible">通用</option>
                <option value="ollama">Ollama 本地</option>
              </select>
            </label>
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
                placeholder={form.model_type === 'ollama' ? 'http://localhost:11434' : 'https://api.example.com/v1'}
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">API SK</span>
              <input
                value={form.api_key || ''}
                onChange={(e) => setForm((prev) => ({ ...prev, api_key: e.target.value }))}
                placeholder={form.model_type === 'ollama' ? 'Ollama 可留空' : 'sk-...'}
                type="password"
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
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
              {sortedConfigs.map((config) => (
                <tr key={config.id} className="border-t border-[var(--color-border)]">
                  <td className="px-4 py-3 text-[var(--color-text)]">
                    <span className="inline-flex items-center gap-2">
                      {config.is_default && <Check size={14} className="text-[var(--color-accent)]" />}
                      {modelTypeLabels[config.model_type]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.provider || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.model_name || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)] max-w-xs truncate">{config.base_url || '-'}</td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">{config.api_key_masked || '-'}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <button title="测试连接" onClick={() => handleTestSaved(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50" disabled={testingId === config.id}>
                        <Zap size={16} />
                      </button>
                      <button title="设为默认" onClick={() => handleSetDefault(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]">
                        <Check size={16} />
                      </button>
                      <button title="编辑" onClick={() => handleEdit(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]">
                        <Pencil size={16} />
                      </button>
                      <button title="删除" onClick={() => handleDelete(config)} className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-danger)]">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {sortedConfigs.length === 0 && (
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
