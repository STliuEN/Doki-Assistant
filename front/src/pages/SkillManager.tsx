import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Save, Trash2, Wrench } from 'lucide-react'
import { chatApi, type ChatSkill, type ChatTool, type SkillDetail } from '../api/chat'

const emptySkill: SkillDetail = {
  id: '',
  label: '',
  description: '',
  tools: [],
  default: true,
  visibility: 'public',
  order: 100,
  instructions: '',
}

const errorMessage = (error: unknown, fallback: string) => (
  error instanceof Error ? error.message : fallback
)

export default function SkillManager() {
  const [skills, setSkills] = useState<ChatSkill[]>([])
  const [tools, setTools] = useState<ChatTool[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [form, setForm] = useState<SkillDetail>(emptySkill)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const selectedExists = useMemo(
    () => skills.some((skill) => skill.id === selectedId),
    [skills, selectedId]
  )

  const loadCatalog = useCallback(async () => {
    let res
    try {
      res = await chatApi.skillCatalog()
    } catch {
      res = await chatApi.skills()
    }
    const catalog = res.data
    setSkills(catalog?.skills || [])
    setTools(catalog?.tools || [])
    if (!selectedId && catalog?.skills?.length) {
      setSelectedId(catalog.skills[0].id)
    }
  }, [selectedId])

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(errorMessage(error, '加载 skill 列表失败')))
  }, [loadCatalog])

  useEffect(() => {
    if (!selectedId) {
      setForm(emptySkill)
      return
    }
    setLoading(true)
    chatApi.skillDetail(selectedId)
      .then((res) => {
        if (res.data) setForm(res.data)
      })
      .catch((error) => setMessage(errorMessage(error, '加载 skill 详情失败')))
      .finally(() => setLoading(false))
  }, [selectedId])

  const startCreate = () => {
    setSelectedId('')
    setForm({ ...emptySkill, instructions: '# 新 Skill\n\n描述这个 skill 的行为规则。\n' })
    setMessage('')
  }

  const toggleTool = (toolId: string) => {
    setForm((current) => ({
      ...current,
      tools: current.tools.includes(toolId)
        ? current.tools.filter((id) => id !== toolId)
        : [...current.tools, toolId],
    }))
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const payload = { ...form, id: form.id.trim() }
      if (selectedExists) {
        await chatApi.updateSkill(selectedId, payload)
        setMessage('Skill 已更新')
      } else {
        await chatApi.createSkill(payload)
        setSelectedId(payload.id)
        setMessage('Skill 已创建')
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
    const ok = window.confirm(`删除 skill「${selectedId}」？`)
    if (!ok) return
    setSaving(true)
    try {
      await chatApi.deleteSkill(selectedId)
      setMessage('Skill 已删除')
      setSelectedId('')
      setForm(emptySkill)
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
            <h1 className="font-heading text-lg text-[var(--color-text)]">Skill</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">管理对话可用能力</p>
          </div>
          <button
            type="button"
            onClick={startCreate}
            className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            title="新增 Skill"
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="space-y-1">
          {skills.map((skill) => (
            <button
              key={skill.id}
              type="button"
              onClick={() => setSelectedId(skill.id)}
              className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                selectedId === skill.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
              }`}
            >
              <div className="text-sm font-medium">{skill.label}</div>
              <div className="text-xs opacity-75 truncate">{skill.id}</div>
            </button>
          ))}
          {skills.length === 0 && (
            <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">
              暂无 Skill。点击右上角新增。
            </div>
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-heading text-xl text-[var(--color-text)]">
                {selectedExists ? form.label || selectedId : '新增 Skill'}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]">
                调整 Skill 的说明、默认启用状态和绑定工具。
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
                disabled={saving || loading}
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
            <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={form.default}
                onChange={(e) => setForm((current) => ({ ...current, default: e.target.checked }))}
              />
              默认启用
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
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <Wrench size={16} />
              绑定工具
            </div>
            <div className="flex flex-wrap gap-2">
              {tools.map((tool) => {
                const active = form.tools.includes(tool.id)
                return (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => toggleTool(tool.id)}
                    title={tool.description}
                    className={`px-2.5 py-1.5 rounded-md border text-xs transition-colors ${
                      active
                        ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                        : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]'
                    }`}
                  >
                    {tool.label}
                  </button>
                )
              })}
            </div>
          </section>

          <section className="space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)]">执行指令</span>
            <textarea
              value={form.instructions}
              onChange={(e) => setForm((current) => ({ ...current, instructions: e.target.value }))}
              rows={16}
              className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm font-mono text-[var(--color-text)] resize-y"
            />
          </section>
        </div>
      </main>
    </div>
  )
}
