import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { chatApi, type ToolDetail } from '../api/chat'

const emptyTool: ToolDetail = {
  id: '',
  label: '',
  description: '',
  category: 'general',
  symbol: '',
  order: 100,
}

const errorMessage = (error: unknown, fallback: string) => (
  error instanceof Error ? error.message : fallback
)

export default function ToolManager() {
  const [tools, setTools] = useState<ToolDetail[]>([])
  const [symbols, setSymbols] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [form, setForm] = useState<ToolDetail>(emptyTool)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const selectedExists = useMemo(
    () => tools.some((tool) => tool.id === selectedId),
    [tools, selectedId]
  )

  const loadCatalog = useCallback(async () => {
    const res = await chatApi.toolCatalog()
    setTools(res.data?.tools || [])
    setSymbols(res.data?.symbols || [])
    if (!selectedId && res.data?.tools?.length) {
      setSelectedId(res.data.tools[0].id)
    }
  }, [selectedId])

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(errorMessage(error, '加载工具列表失败')))
  }, [loadCatalog])

  useEffect(() => {
    const item = tools.find((tool) => tool.id === selectedId)
    if (item) setForm(item)
  }, [selectedId, tools])

  const startCreate = () => {
    setSelectedId('')
    setForm(emptyTool)
    setMessage('')
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const payload = { ...form, id: form.id.trim() }
      if (selectedExists) {
        await chatApi.updateTool(selectedId, payload)
        setMessage('工具已更新')
      } else {
        await chatApi.createTool(payload)
        setSelectedId(payload.id)
        setMessage('工具已创建')
      }
      await loadCatalog()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!selectedExists || !selectedId) return
    const ok = window.confirm(`删除工具「${selectedId}」？`)
    if (!ok) return
    setSaving(true)
    try {
      await chatApi.deleteTool(selectedId)
      setMessage('工具已删除')
      setSelectedId('')
      setForm(emptyTool)
      await loadCatalog()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '删除失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full flex bg-[var(--color-bg)]">
      <aside className="w-72 border-r border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-4 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-lg text-[var(--color-text)]">工具库</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">管理可供 Skill 调用的工具</p>
          </div>
          <button
            type="button"
            onClick={startCreate}
            className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            title="新增工具"
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="space-y-1">
          {tools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              onClick={() => setSelectedId(tool.id)}
              className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                selectedId === tool.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
              }`}
            >
              <div className="text-sm font-medium">{tool.label}</div>
              <div className="text-xs opacity-75 truncate">{tool.id}</div>
            </button>
          ))}
          {tools.length === 0 && (
            <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">
              暂无工具。点击右上角新增。
            </div>
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-heading text-xl text-[var(--color-text)]">
                {selectedExists ? form.label || selectedId : '新增工具'}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]">
                维护工具的展示信息，并选择对应的执行能力。
              </p>
            </div>
            <div className="flex items-center gap-2">
              {selectedExists && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={saving}
                  className="h-9 inline-flex items-center gap-2 px-3 rounded-md border border-[var(--color-border)] text-[var(--color-danger)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
                >
                  <Trash2 size={15} />
                  删除
                </button>
              )}
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="h-9 inline-flex items-center gap-2 px-3 rounded-md bg-[var(--color-accent)] text-white hover:bg-blue-700 disabled:opacity-50"
              >
                <Save size={15} />
                保存
              </button>
            </div>
          </div>

          {message && (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 text-sm text-[var(--color-text-secondary)]">
              {message}
            </div>
          )}

          <section className="grid grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">ID</span>
              <input
                value={form.id}
                onChange={(e) => setForm((current) => ({ ...current, id: e.target.value }))}
                disabled={selectedExists}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">名称</span>
              <input
                value={form.label}
                onChange={(e) => setForm((current) => ({ ...current, label: e.target.value }))}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
            <label className="space-y-1 col-span-2">
              <span className="text-xs text-[var(--color-text-secondary)]">描述</span>
              <input
                value={form.description}
                onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">分类</span>
              <input
                value={form.category}
                onChange={(e) => setForm((current) => ({ ...current, category: e.target.value }))}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">排序</span>
              <input
                type="number"
                value={form.order}
                onChange={(e) => setForm((current) => ({ ...current, order: Number(e.target.value) }))}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              />
            </label>
            <label className="space-y-1 col-span-2">
              <span className="text-xs text-[var(--color-text-secondary)]">工具实现</span>
              <select
                value={form.symbol}
                onChange={(e) => setForm((current) => ({ ...current, symbol: e.target.value }))}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)]"
              >
                <option value="">选择工具实现</option>
                {symbols.map((symbol) => (
                  <option key={symbol} value={symbol}>{symbol}</option>
                ))}
              </select>
            </label>
          </section>
        </div>
      </main>
    </div>
  )
}
