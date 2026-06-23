import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { chatApi, type McpServer, type ToolDetail } from '../api/chat'

type Selection = { type: 'tool' | 'server'; id: string }

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

const emptyServer: McpServer = {
  id: '',
  label: '',
  description: '',
  enabled: false,
  transport: 'stdio',
  url: '',
  command: '',
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
  const [mcpServers, setMcpServers] = useState<McpServer[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [creating, setCreating] = useState(false)
  const [toolForm, setToolForm] = useState<ToolDetail>(emptyTool)
  const [serverForm, setServerForm] = useState<McpServer>(emptyServer)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [canManageMcp, setCanManageMcp] = useState(false)

  const localTools = useMemo(
    () => tools.filter((tool) => tool.source !== 'mcp'),
    [tools]
  )
  const mcpToolsByServer = useMemo(() => {
    const grouped = new Map<string, ToolDetail[]>()
    for (const tool of tools) {
      if (tool.source !== 'mcp') continue
      const serverId = tool.provider_id || ''
      const current = grouped.get(serverId) || []
      current.push(tool)
      grouped.set(serverId, current)
    }
    return grouped
  }, [tools])
  const selectedTool = useMemo(
    () => selection?.type === 'tool' ? tools.find((tool) => tool.id === selection.id) : undefined,
    [selection, tools]
  )
  const selectedServer = useMemo(
    () => selection?.type === 'server' ? mcpServers.find((server) => server.id === selection.id) : undefined,
    [mcpServers, selection]
  )
  const toolServer = useMemo(
    () => mcpServers.find((server) => server.id === toolForm.provider_id),
    [mcpServers, toolForm.provider_id]
  )
  const isToolView = creating || selection?.type === 'tool'
  const isServerView = selection?.type === 'server' && !creating
  const isMcpTool = isToolView && toolForm.source === 'mcp'
  const isReadOnlyMcp = isMcpTool && !canManageMcp
  const canEditServerUrl = (
    canManageMcp &&
    Boolean(serverForm.transport) &&
    serverForm.transport !== 'stdio'
  )

  const loadCatalog = useCallback(async (nextSelection?: Selection) => {
    const [toolRes, serverRes] = await Promise.all([
      chatApi.toolCatalog(),
      chatApi.mcpServers().catch(() => ({ data: { servers: [] } })),
    ])
    const nextTools = toolRes.data?.tools || []
    const nextServers = serverRes.data?.servers || []
    setTools(nextTools)
    setMcpServers(nextServers)

    if (nextSelection) {
      setSelection(nextSelection)
      return
    }
    setSelection((current) => {
      if (current?.type === 'tool' && nextTools.some((tool) => tool.id === current.id)) return current
      if (current?.type === 'server' && nextServers.some((server) => server.id === current.id)) return current
      if (nextTools.length > 0) return { type: 'tool', id: nextTools[0].id }
      if (nextServers.length > 0) return { type: 'server', id: nextServers[0].id }
      return null
    })
  }, [])

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(errorMessage(error, '加载工具列表失败')))
    chatApi.mcpPermissions()
      .then((res) => setCanManageMcp(Boolean(res.data?.can_manage_mcp)))
      .catch(() => setCanManageMcp(false))
  }, [loadCatalog])

  useEffect(() => {
    if (creating) return
    if (selectedTool) setToolForm(selectedTool)
  }, [creating, selectedTool])

  useEffect(() => {
    if (selectedServer) setServerForm(selectedServer)
  }, [selectedServer])

  const startCreate = () => {
    const index = tools.length + 1
    const id = slugifyId(`custom_tool_${index}`, `custom_tool_${index}`)
    setCreating(true)
    setSelection(null)
    setToolForm({
      ...emptyTool,
      id,
      label: '新工具',
      description: '描述这个工具可以完成的动作。',
      instructions: '# 新工具\n\n描述这个工具的使用规则、输入参数和返回结果。\n',
    })
    setMessage('')
  }

  const saveTool = async () => {
    if (isMcpTool && !canManageMcp) {
      setMessage('MCP 工具只有管理员可以修改')
      return
    }
    const payload = { ...toolForm, id: toolForm.id.trim() }
    if (isMcpTool) {
      await chatApi.updateMcpTool(payload.id, {
        label: payload.label,
        description: payload.description,
        enabled: payload.enabled,
        risk_level: payload.risk_level,
        requires_confirmation: payload.requires_confirmation,
        timeout_seconds: payload.timeout_seconds,
        max_output_chars: payload.max_output_chars,
      })
      setMessage('MCP 工具配置已更新')
      await loadCatalog({ type: 'tool', id: payload.id })
      return
    }
    if (selection?.type === 'tool' && tools.some((tool) => tool.id === selection.id)) {
      await chatApi.updateTool(selection.id, payload)
      setMessage('工具已更新')
    } else {
      await chatApi.createTool(payload)
      setCreating(false)
      setMessage('工具已创建')
    }
    await loadCatalog({ type: 'tool', id: payload.id })
  }

  const saveServer = async () => {
    if (!canManageMcp || !serverForm.id) {
      setMessage('MCP Server 只有管理员可以修改')
      return
    }
    await chatApi.updateMcpServer(serverForm.id, {
      enabled: serverForm.enabled,
      label: serverForm.label || serverForm.id,
      description: serverForm.description || '',
      ...(serverForm.transport !== 'stdio' && serverForm.url ? { url: serverForm.url } : {}),
    })
    setMessage('MCP Server 配置已更新')
    await loadCatalog({ type: 'server', id: serverForm.id })
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      if (isServerView) {
        await saveServer()
      } else {
        await saveTool()
      }
    } catch (error) {
      setMessage(errorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (creating || !selection) return
    if (selection.type === 'tool') {
      const target = selectedTool
      if (!target) return
      const ok = window.confirm(
        target.source === 'mcp'
          ? `从当前项目移除 MCP 工具「${target.label || target.id}」？`
          : `删除工具「${target.id}」？`
      )
      if (!ok) return
      setSaving(true)
      try {
        if (target.source === 'mcp') {
          await chatApi.deleteMcpTool(target.id)
          setMessage('MCP 工具已从当前项目移除')
        } else {
          await chatApi.deleteTool(target.id)
          setMessage('工具已删除')
        }
        setSelection(null)
        setToolForm(emptyTool)
        await loadCatalog()
      } catch (error) {
        setMessage(errorMessage(error, '删除失败'))
      } finally {
        setSaving(false)
      }
      return
    }

    if (!canManageMcp || !selectedServer) return
    const ok = window.confirm(
      `移除 MCP Server 接入「${selectedServer.label || selectedServer.id}」？这会同时移除它下面的 MCP 工具入口，但不会删除外部 server 文件。`
    )
    if (!ok) return
    setSaving(true)
    try {
      await chatApi.deleteMcpServer(selectedServer.id)
      setMessage('MCP Server 接入已移除')
      setSelection(null)
      setServerForm(emptyServer)
      await loadCatalog()
    } catch (error) {
      setMessage(errorMessage(error, '删除失败'))
    } finally {
      setSaving(false)
    }
  }

  const canSave = isServerView ? canManageMcp : !isReadOnlyMcp
  const canRemove = Boolean(
    !creating &&
    selection &&
    (selection.type === 'tool'
      ? selectedTool && (selectedTool.source !== 'mcp' || canManageMcp)
      : canManageMcp)
  )
  const removeLabel = selection?.type === 'server'
    ? '移除接入'
    : selectedTool?.source === 'mcp'
      ? '移除'
      : '删除'

  return (
    <div className="h-full flex bg-[var(--color-bg)]">
      <aside className="w-72 border-r border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-4 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-lg text-[var(--color-text)]">工具库</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">管理本地工具和 MCP 接入</p>
          </div>
          <button
            type="button"
            onClick={startCreate}
            className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            title="新增本地工具"
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="space-y-1">
          <div className="px-3 pt-1 text-[11px] font-medium uppercase text-[var(--color-text-secondary)]">
            本地工具
          </div>
          {localTools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              onClick={() => {
                setCreating(false)
                setSelection({ type: 'tool', id: tool.id })
              }}
              className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                selection?.type === 'tool' && selection.id === tool.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{tool.label}</span>
                <span className="shrink-0 text-[11px] opacity-70">
                  {tool.enabled === false ? 'disabled' : '本地'}
                </span>
              </div>
              <div className="text-xs opacity-75 truncate">{tool.id}</div>
            </button>
          ))}
          {localTools.length === 0 && (
            <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">暂无工具</div>
          )}
        </div>

        <div className="space-y-1">
          <div className="px-3 pt-2 text-[11px] font-medium uppercase text-[var(--color-text-secondary)]">
            MCP
          </div>
          {mcpServers.map((server) => (
            <div key={server.id} className="space-y-1">
              <button
                type="button"
                onClick={() => {
                  setCreating(false)
                  setSelection({ type: 'server', id: server.id })
                }}
                className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                  selection?.type === 'server' && selection.id === server.id
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                    : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{server.label || server.id}</span>
                  <span className="shrink-0 text-[11px] opacity-70">
                    {server.enabled ? server.transport : 'disabled'}
                  </span>
                </div>
                <div className="text-xs opacity-75 truncate">{server.id}</div>
              </button>
              <div className="ml-3 border-l border-[var(--color-border)] pl-2 space-y-1">
                {(mcpToolsByServer.get(server.id) || []).map((tool) => (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => {
                      setCreating(false)
                      setSelection({ type: 'tool', id: tool.id })
                    }}
                    className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                      selection?.type === 'tool' && selection.id === tool.id
                        ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                        : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm">{tool.label}</span>
                      <span className="shrink-0 text-[11px] opacity-70">
                        {tool.enabled === false ? 'disabled' : 'tool'}
                      </span>
                    </div>
                    <div className="text-xs opacity-75 truncate">{tool.external_name || tool.id}</div>
                  </button>
                ))}
                {(mcpToolsByServer.get(server.id) || []).length === 0 && (
                  <div className="px-3 py-2 text-xs text-[var(--color-text-secondary)]">
                    暂无已发现工具
                  </div>
                )}
              </div>
            </div>
          ))}
          {mcpServers.length === 0 && (
            <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">暂无 MCP Server</div>
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-heading text-xl text-[var(--color-text)]">
                {isServerView
                  ? serverForm.label || serverForm.id || 'MCP Server'
                  : creating
                    ? '新增工具'
                    : toolForm.label || toolForm.id || '工具'}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {isServerView
                  ? '维护 MCP Server 的连接元数据和启用状态。'
                  : isMcpTool
                    ? 'MCP 工具由外部 server 提供；这里维护项目侧展示和运行边界。'
                    : '维护本地工具的展示信息和执行说明。'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {canRemove && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={saving}
                  className="h-9 inline-flex items-center gap-2 px-3 rounded-md border border-[var(--color-border)] text-[var(--color-danger)] hover:bg-[var(--color-bg-secondary)] disabled:opacity-50"
                >
                  <Trash2 size={15} />
                  {removeLabel}
                </button>
              )}
              <button
                type="button"
                onClick={save}
                disabled={saving || !canSave}
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

          {isServerView ? (
            <section className="grid grid-cols-2 gap-4">
              <div className="col-span-2 grid grid-cols-3 gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
                <span>类型：MCP Server</span>
                <span>状态：{serverForm.status || '-'}</span>
                <span>连接：{serverForm.transport || '-'}</span>
              </div>
              {serverForm.last_error && (
                <div className="col-span-2 rounded-md border border-[var(--color-danger)] px-3 py-2 text-sm text-[var(--color-danger)]">
                  {serverForm.last_error}
                </div>
              )}
              <label className="space-y-1">
                <span className="text-xs text-[var(--color-text-secondary)]">ID</span>
                <input
                  value={serverForm.id}
                  disabled
                  className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-[var(--color-text-secondary)]">名称</span>
                <input
                  value={serverForm.label}
                  onChange={(e) => setServerForm((current) => ({ ...current, label: e.target.value }))}
                  disabled={!canManageMcp}
                  className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-[var(--color-text-secondary)]">连接方式</span>
                <input
                  value={serverForm.transport}
                  disabled
                  className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-[var(--color-text-secondary)]">
                  {serverForm.transport === 'stdio' ? '命令' : 'URL / IP'}
                </span>
                <input
                  value={serverForm.transport === 'stdio' ? serverForm.command || '' : serverForm.url || ''}
                  onChange={(e) => setServerForm((current) => ({ ...current, url: e.target.value }))}
                  disabled={!canEditServerUrl}
                  className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                />
              </label>
              <label className="space-y-1 col-span-2">
                <span className="text-xs text-[var(--color-text-secondary)]">描述</span>
                <input
                  value={serverForm.description || ''}
                  onChange={(e) => setServerForm((current) => ({ ...current, description: e.target.value }))}
                  disabled={!canManageMcp}
                  className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                />
              </label>
              <label className="col-span-2 inline-flex items-center gap-2 text-sm text-[var(--color-text)]">
                <input
                  type="checkbox"
                  checked={Boolean(serverForm.enabled)}
                  onChange={(e) => setServerForm((current) => ({ ...current, enabled: e.target.checked }))}
                  disabled={!canManageMcp}
                  className="h-4 w-4"
                />
                启用 MCP Server
              </label>
            </section>
          ) : (
            <>
              <section className="grid grid-cols-2 gap-4">
                <div className="col-span-2 grid grid-cols-3 gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
                  <span>来源：{sourceLabel(toolForm)}</span>
                  <span>Server：{toolServer?.label || toolForm.provider_id || '-'}</span>
                  <span>外部名：{toolForm.external_name || '-'}</span>
                </div>
                {toolForm.last_error && (
                  <div className="col-span-2 rounded-md border border-[var(--color-danger)] px-3 py-2 text-sm text-[var(--color-danger)]">
                    {toolForm.last_error}
                  </div>
                )}
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">ID</span>
                  <input
                    value={toolForm.id}
                    onChange={(e) => setToolForm((current) => ({ ...current, id: e.target.value }))}
                    disabled={!creating || isMcpTool}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">名称</span>
                  <input
                    value={toolForm.label}
                    onChange={(e) => setToolForm((current) => ({ ...current, label: e.target.value }))}
                    disabled={isReadOnlyMcp}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1 col-span-2">
                  <span className="text-xs text-[var(--color-text-secondary)]">描述</span>
                  <input
                    value={toolForm.description}
                    onChange={(e) => setToolForm((current) => ({ ...current, description: e.target.value }))}
                    disabled={isReadOnlyMcp}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">分类</span>
                  <input
                    value={toolForm.category}
                    onChange={(e) => setToolForm((current) => ({ ...current, category: e.target.value }))}
                    disabled={isMcpTool}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">排序</span>
                  <input
                    type="number"
                    value={toolForm.order}
                    onChange={(e) => setToolForm((current) => ({ ...current, order: Number(e.target.value) }))}
                    disabled={isMcpTool}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">风险等级</span>
                  <select
                    value={toolForm.risk_level || 'low'}
                    onChange={(e) => setToolForm((current) => ({
                      ...current,
                      risk_level: e.target.value as ToolDetail['risk_level'],
                    }))}
                    disabled={isReadOnlyMcp}
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
                    value={toolForm.timeout_seconds || 600}
                    onChange={(e) => setToolForm((current) => ({ ...current, timeout_seconds: Number(e.target.value) }))}
                    disabled={isReadOnlyMcp}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-[var(--color-text-secondary)]">最大输出字符</span>
                  <input
                    type="number"
                    min={256}
                    max={100000}
                    value={toolForm.max_output_chars || 4000}
                    onChange={(e) => setToolForm((current) => ({ ...current, max_output_chars: Number(e.target.value) }))}
                    disabled={isReadOnlyMcp}
                    className="w-full h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:opacity-60"
                  />
                </label>
                <label className="col-span-2 inline-flex items-center gap-2 text-sm text-[var(--color-text)]">
                  <input
                    type="checkbox"
                    checked={Boolean(toolForm.requires_confirmation)}
                    onChange={(e) => setToolForm((current) => ({ ...current, requires_confirmation: e.target.checked }))}
                    disabled={isReadOnlyMcp}
                    className="h-4 w-4"
                  />
                  需要用户二次确认
                </label>
                {isMcpTool && (
                  <label className="col-span-2 inline-flex items-center gap-2 text-sm text-[var(--color-text)]">
                    <input
                      type="checkbox"
                      checked={toolForm.enabled !== false}
                      onChange={(e) => setToolForm((current) => ({ ...current, enabled: e.target.checked }))}
                      disabled={isReadOnlyMcp}
                      className="h-4 w-4"
                    />
                    启用 MCP 工具
                  </label>
                )}
              </section>

              <section className="space-y-1">
                <span className="text-xs text-[var(--color-text-secondary)]">执行说明</span>
                <textarea
                  value={isMcpTool ? (toolForm.instructions || toolForm.description || '') : toolForm.instructions}
                  onChange={(e) => setToolForm((current) => ({ ...current, instructions: e.target.value }))}
                  disabled={isMcpTool}
                  rows={12}
                  className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] resize-y disabled:opacity-60"
                />
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
