import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  Archive,
  Bell,
  CalendarClock,
  CheckCircle2,
  Circle,
  Clock3,
  FilePlus2,
  GraduationCap,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { memoryApi } from '../api/memory'
import type { MemoryItem, MemoryPayload, MemoryQuestion, MemoryType } from '../types/api'
import EmptyState from '../components/common/EmptyState'

type FilterKey = 'today' | 'all' | MemoryType | 'done'

const filterOptions: { key: FilterKey; label: string }[] = [
  { key: 'today', label: '今日' },
  { key: 'all', label: '全部' },
  { key: 'review', label: '复习' },
  { key: 'todo', label: '待办' },
  { key: 'reminder', label: '提醒' },
  { key: 'long_term', label: '长期事项' },
  { key: 'memo', label: '备忘' },
  { key: 'done', label: '已完成' },
]

const typeLabels: Record<MemoryType, string> = {
  review: '复习',
  todo: '待办',
  reminder: '提醒',
  long_term: '长期事项',
  memo: '备忘',
}

const typeIcons: Record<MemoryType, typeof Circle> = {
  review: GraduationCap,
  todo: CheckCircle2,
  reminder: Bell,
  long_term: CalendarClock,
  memo: Clock3,
}

const initialForm: MemoryPayload = {
  type: 'memo',
  title: '',
  content: '',
  priority: 'medium',
  due_at: '',
}

function formatDate(value?: string | null) {
  if (!value) return '无时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function MemoryCenter() {
  const [items, setItems] = useState<MemoryItem[]>([])
  const [filter, setFilter] = useState<FilterKey>('today')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<MemoryPayload>(initialForm)
  const [quizNotes, setQuizNotes] = useState<Record<string, MemoryQuestion>>({})
  const [selectedAnswer, setSelectedAnswer] = useState<Record<string, string>>({})
  const [questionLoading, setQuestionLoading] = useState<string | null>(null)

  const loadItems = async (nextFilter = filter) => {
    setLoading(true)
    try {
      if (nextFilter === 'today') {
        const data = await memoryApi.today()
        setItems(data.memories || [])
      } else if (nextFilter === 'all') {
        const data = await memoryApi.list()
        setItems(data.memories || [])
      } else if (nextFilter === 'done') {
        const data = await memoryApi.list({ status: 'done' })
        setItems(data.memories || [])
      } else {
        const data = await memoryApi.list({ type: nextFilter, status: 'active' })
        setItems(data.memories || [])
      }
    } catch {
      toast.error('加载记忆事项失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadItems()
  }, [])

  const counts = useMemo(() => {
    const result: Record<string, number> = {}
    for (const item of items) {
      result[item.type] = (result[item.type] || 0) + 1
    }
    return result
  }, [items])

  const handleFilter = (key: FilterKey) => {
    setFilter(key)
    void loadItems(key)
  }

  const handleCreate = async () => {
    if (!form.title.trim()) {
      toast.error('请填写标题')
      return
    }
    try {
      await memoryApi.create({
        ...form,
        due_at: form.due_at || undefined,
        content: form.content || '',
      })
      toast.success('记忆事项已创建')
      setForm(initialForm)
      setCreating(false)
      void loadItems()
    } catch {
      toast.error('创建失败')
    }
  }

  const handleComplete = async (id: string) => {
    await memoryApi.complete(id)
    toast.success('已完成')
    void loadItems()
  }

  const handleReviewed = async (id: string) => {
    await memoryApi.reviewed(id)
    toast.success('已标记复习完成')
    void loadItems()
  }

  const handlePostpone = async (id: string) => {
    await memoryApi.postpone(id, 1)
    toast.success('已延期 1 天')
    void loadItems()
  }

  const handleArchive = async (id: string) => {
    await memoryApi.archive(id)
    toast.success('已归档')
    void loadItems()
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定要删除这条记忆事项吗？')) return
    await memoryApi.delete(id)
    toast.success('已删除')
    void loadItems()
  }

  const handleStartQuiz = async (item: MemoryItem) => {
    if (quizNotes[item.id]) return
    setQuestionLoading(item.id)
    try {
      const question = await memoryApi.getReviewQuestion(item.id)
      setQuizNotes((prev) => ({ ...prev, [item.id]: question }))
    } catch {
      toast.error('获取题目失败')
    } finally {
      setQuestionLoading(null)
    }
  }

  return (
    <div className="h-full flex flex-col bg-[var(--color-bg)]">
      <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="font-heading text-xl font-semibold text-[var(--color-text)]">记忆中心</h1>
            <p className="mt-1 text-sm text-[var(--color-text-tertiary)]">复习、待办、提醒和长期事项统一管理</p>
          </div>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-2 rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm text-white"
          >
            <FilePlus2 size={16} />
            新建
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {filterOptions.map((item) => (
            <button
              key={item.key}
              onClick={() => handleFilter(item.key)}
              className={`rounded-md border px-3 py-1.5 text-sm ${
                filter === item.key
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              {item.label}
              {counts[item.key] ? <span className="ml-1 text-xs opacity-70">{counts[item.key]}</span> : null}
            </button>
          ))}
        </div>
      </div>

      {creating && (
        <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4">
          <div className="grid gap-3 md:grid-cols-[160px_1fr_180px_160px_auto]">
            <select
              value={form.type}
              onChange={(event) => setForm((prev) => ({ ...prev, type: event.target.value as MemoryType }))}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            >
              {Object.entries(typeLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <input
              value={form.title}
              onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              placeholder="标题"
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            />
            <input
              type="datetime-local"
              value={form.due_at || ''}
              onChange={(event) => setForm((prev) => ({ ...prev, due_at: event.target.value }))}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            />
            <select
              value={form.priority}
              onChange={(event) => setForm((prev) => ({ ...prev, priority: event.target.value as MemoryPayload['priority'] }))}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
            >
              <option value="low">低优先级</option>
              <option value="medium">中优先级</option>
              <option value="high">高优先级</option>
            </select>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm text-white">保存</button>
              <button onClick={() => setCreating(false)} className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm">取消</button>
            </div>
          </div>
          <textarea
            value={form.content || ''}
            onChange={(event) => setForm((prev) => ({ ...prev, content: event.target.value }))}
            placeholder="补充内容"
            rows={2}
            className="mt-3 w-full resize-none rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
          />
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-[var(--color-text-tertiary)]">
            <Loader2 size={20} className="mr-2 animate-spin" />
            加载中...
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={<Clock3 size={48} />} message="没有符合条件的记忆事项" />
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const Icon = typeIcons[item.type] || Clock3
              const question = quizNotes[item.id]
              const selected = selectedAnswer[item.id]
              return (
                <div key={item.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Icon size={16} className="text-[var(--color-accent)]" />
                        <span className="rounded bg-[var(--color-bg-secondary)] px-2 py-0.5 text-xs text-[var(--color-text-secondary)]">
                          {typeLabels[item.type]}
                        </span>
                        <span className="text-xs text-[var(--color-text-tertiary)]">{formatDate(item.due_at || item.remind_at)}</span>
                      </div>
                      <h3 className="mt-2 text-base font-medium text-[var(--color-text)]">{item.title}</h3>
                      {item.content && (
                        <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--color-text-secondary)]">{item.content}</p>
                      )}
                      {item.type === 'review' && (
                        <p className="mt-2 text-xs text-[var(--color-text-tertiary)]">
                          第 {item.review_count || 0} 次复习，当前间隔 {item.interval_days || 1} 天
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {item.type === 'review' ? (
                        <>
                          <button
                            onClick={() => handleStartQuiz(item)}
                            className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs hover:bg-[var(--color-bg-secondary)]"
                          >
                            {questionLoading === item.id ? <Loader2 size={12} className="inline animate-spin" /> : '题目'}
                          </button>
                          <button onClick={() => handleReviewed(item.id)} className="rounded-md bg-[var(--color-success)] px-3 py-1.5 text-xs text-white">
                            已复习
                          </button>
                        </>
                      ) : (
                        <button onClick={() => handleComplete(item.id)} className="rounded-md bg-[var(--color-success)] px-3 py-1.5 text-xs text-white">
                          完成
                        </button>
                      )}
                      <button onClick={() => handlePostpone(item.id)} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs hover:bg-[var(--color-bg-secondary)]">
                        延期
                      </button>
                      <button onClick={() => handleArchive(item.id)} className="rounded-md border border-[var(--color-border)] p-1.5 hover:bg-[var(--color-bg-secondary)]" title="归档">
                        <Archive size={14} />
                      </button>
                      <button onClick={() => handleDelete(item.id)} className="rounded-md border border-[var(--color-border)] p-1.5 text-[var(--color-danger)] hover:bg-[var(--color-bg-secondary)]" title="删除">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {question && (
                    <div className="mt-4 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-[var(--color-text)]">{question.question}</p>
                        <button
                          onClick={() => {
                            setQuizNotes((prev) => {
                              const next = { ...prev }
                              delete next[item.id]
                              return next
                            })
                            void handleStartQuiz(item)
                          }}
                          className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text)]"
                          title="重新生成"
                        >
                          <RefreshCw size={14} />
                        </button>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {question.choices.map((choice) => {
                          const active = selected === choice
                          const correct = selected && choice === question.answer
                          const wrong = active && choice !== question.answer
                          return (
                            <button
                              key={choice}
                              onClick={() => setSelectedAnswer((prev) => ({ ...prev, [item.id]: choice }))}
                              className={`rounded-md border px-3 py-2 text-left text-sm ${
                                correct
                                  ? 'border-[var(--color-success)] bg-[var(--color-success-bg)] text-[var(--color-success)]'
                                  : wrong
                                    ? 'border-[var(--color-danger)] bg-[var(--color-danger-bg)] text-[var(--color-danger)]'
                                    : 'border-[var(--color-border)] hover:bg-[var(--color-bg-secondary)]'
                              }`}
                            >
                              {choice}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
