import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { chatApi, type ToolDetail } from '../api/chat'

const emptyTool: ToolDetail = {
  id: '',
  label: '',
  description: '',
  category: 'general',
  order: 100,
  risk_level: 'low',
  requires_confirmation: false,
  timeout_seconds: 600,
  max_output_chars: 4000,
  instructions: '',
  source: 'local',
}

const errorMessage = (error: unknown, fallback: string) => (
  error instanceof Error ? error.message : fallback
)

const slugifyId = (value: string, fallback: string) => {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
  const id = /^[a-z]/.test(normalized) ? normalized : fallback
  return id.slice(0, 64)
}

const sourceLabel = (tool: ToolDetail) => (tool.source === 'mcp' ? 'MCP' : '本地')

export default function ToolManager() {
  const [tools, setTools] = useState<ToolDetail[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<ToolDetail>(emptyTool)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const selectedExists = useMemo(
    () => tools.some((tool) => tool.id === selectedId),
    [tools, selectedId]
  )
  const isMcpTool = form.source === 'mcp'

  const loadCatalog = useCallback(async (nextSelectedId?: string) => {
    const res = await chatApi.toolCatalog()
    setTools(res.data?.tools || [])
    if (nextSelectedId) {
      setSelectedId(nextSelectedId)
    }
  }, [])

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(errorMessage(error, '加载工具列表失败')))
  }, [loadCatalog])

  useEffect(() => {
    if (!creating && !selectedId && tools.length > 0) {
      setSelectedId(tools[0].id)
    }
  }, [creating, selectedId, tools])

  useEffect(() => {
    if (creating) return
    const item = tools.find((tool) => tool.id === selectedId)
    if (item) setForm(item)
  }, [creating, selectedId, tools])

  const startCreate = () => {
    const index = tools.length + 1
    const id = slugifyId(`custom_tool_${index}`, `custom_tool_${index}`)
    setCreating(true)
    setSelectedId('')
    setForm({
      ...emptyTool,
      id,
      label: '新工具',
      description: '描述这个工具可以完成的动作。',
      instructions: '# 新工具\n\n描述这个工具的使用规则、输入参数和返回结果。\n',
    })
    setMessage('')
  }

  const save = async () => {
    if (isMcpTool) {
      setMessage('MCP 工具由 MCP 配置管理，当前页面只读')
      return
    }
    setSaving(true)
    setMessage('')
    try {
      const payload = { ...form, id: form.id.trim() }
      if (selectedExists) {
        await chatApi.updateTool(selectedId, payload)
        setMessage('工具已更新')
      } else {
        await chatApi.createTool(payload)
        setCreating(false)
        setSelectedId(payload.id)
        setMessage('工具已创建')
      }
      await loadCatalog(payload.id)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!selectedExists || !selectedId || isMcpTool) return
    const ok = window.confirm(`删除工具「${selectedId}」？`)
    if (!ok) return
    setSaving(true)
    try {
      await chatApi.deleteTool(selectedId)
      setMessage('工具已删除')
      setCreating(false)
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
              onClick={() => {
                setCreating(false)
                setSelectedId(tool.id)
              }}
              className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                selectedId === tool.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{tool.label}</span>
                <span className="shrink-0 text-[11px] opacity-70">{sourceLabel(tool)}</span>
              </div>
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
                {isMcpTool ? 'MCP 工具由外部 server 提供，当前页面只读。' : '维护工具的展示信息和执行说明。'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {selectedExists && !isMcpTool && (
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
                disabled={saving || isMcpTool}
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
            <div className="col-span-2 grid grid-cols-3 gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
              <span>来源：{sourceLabel(form)}</span>
              <span>Server：{form.provider_id || '-'}</span>
              <span>外部名：{form.external_name || '-'}</span>
            </div>
            {form.last_error && (
              <div className="col-span-2 rounded-md border border-[var(--color-danger)] px-3 py-2 text-sm text-[var(--color-danger)]">
                {form.last_error}
              </div>
            )}
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">ID</span>
              <input
                value={form.id}
                onChange={(e) => setForm((current) => ({ ...current, id: e.target.value }))}
                disabled={selectedExists || isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">名称</span>
              <input
                value={form.label}
                onChange={(e) => setForm((current) => ({ ...current, label: e.target.value }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1 col-span-2">
              <span className="text-xs text-[var(--color-text-secondary)]">描述</span>
              <input
                value={form.description}
                onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">分类</span>
              <input
                value={form.category}
                onChange={(e) => setForm((current) => ({ ...current, category: e.target.value }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">排序</span>
              <input
                type="number"
                value={form.order}
                onChange={(e) => setForm((current) => ({ ...current, order: Number(e.target.value) }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">风险等级</span>
              <select
                value={form.risk_level || 'low'}
                onChange={(e) => setForm((current) => ({
                  ...current,
                  risk_level: e.target.value as ToolDetail['risk_level'],
                }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              >
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">超时秒数</span>
              <input
                type="number"
                min={1}
                max={600}
                value={form.timeout_seconds || 600}
                onChange={(e) => setForm((current) => ({ ...current, timeout_seconds: Number(e.target.value) }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-[var(--color-text-secondary)]">最大输出字符</span>
              <input
                type="number"
                min={256}
                max={100000}
                value={form.max_output_chars || 4000}
                onChange={(e) => setForm((current) => ({ ...current, max_output_chars: Number(e.target.value) }))}
                disabled={isMcpTool}
                className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
              />
            </label>
            <label className="col-span-2 inline-flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={Boolean(form.requires_confirmation)}
                onChange={(e) => setForm((current) => ({ ...current, requires_confirmation: e.target.checked }))}
                disabled={isMcpTool}
                className="h-4 w-4"
              />
              需要用户二次确认
            </label>
          </section>

          <section className="space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)]">执行说明</span>
            <textarea
              value={isMcpTool ? (form.instructions || form.description || '') : form.instructions}
              onChange={(e) => setForm((current) => ({ ...current, instructions: e.target.value }))}
              disabled={isMcpTool}
              rows={12}
              className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] resize-y disabled:opacity-60"
            />
          </section>
        </div>
      </main>
    </div>
  )
}
