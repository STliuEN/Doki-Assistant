import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive,
  CheckCircle2,
  ChevronRight,
  Download,
  FileArchive,
  FileText,
  History,
  Package,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
  Undo2,
  Upload,
  Wrench,
} from 'lucide-react'
import {
  chatApi,
  type ChatSkill,
  type ChatTool,
  type SkillCompatibility,
  type SkillDetail,
  type SkillImportResult,
  type SkillOrigin,
  type SkillResource,
  type SkillResourceChanges,
  type SkillResourceInput,
  type SkillSettingsPayload,
  type SkillVersion,
} from '../api/chat'

type ManagerTab = 'content' | 'settings' | 'versions'
type PendingDraft = { id: string; revision: number; snapshot: string; resources: SkillResource[] }
type PendingResource = SkillResource & SkillResourceInput
type ResourceEditState = { upsert: PendingResource[]; delete: string[] }

const MAX_RESOURCE_BYTES = 8 * 1024 * 1024
const MAX_RESOURCE_TOTAL_BYTES = 32 * 1024 * 1024
const MAX_RESOURCE_FILES = 255

const emptyResourceChanges = (): ResourceEditState => ({ upsert: [], delete: [] })

const emptySkill: SkillDetail = {
  id: '',
  label: '',
  description: '',
  tools: [],
  default: false,
  enabled: false,
  visibility: 'public',
  order: 100,
  instructions: '',
  always_on: false,
  routable: true,
  routing_examples: { positive: [], negative: [] },
}

const inputClass = 'w-full min-h-10 px-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-60'
const secondaryButtonClass = 'h-9 inline-flex items-center justify-center gap-2 px-3 rounded-md border border-[var(--color-border)] text-sm text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-50'

const errorMessage = (error: unknown, fallback: string) => (
  error instanceof Error ? error.message : fallback
)

const cloneSkill = (skill: SkillDetail): SkillDetail => ({
  ...skill,
  tools: [...skill.tools],
  frontmatter: { ...(skill.frontmatter || {}) },
  resources: (skill.resources || []).map((resource) => ({ ...resource })),
  routing_examples: {
    positive: [...(skill.routing_examples.positive || [])],
    negative: [...(skill.routing_examples.negative || [])],
  },
})

const slugifyName = (value: string, fallback: string) => {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  const name = /^[a-z0-9]/.test(normalized) ? normalized : fallback
  return name.slice(0, 64).replace(/-+$/g, '')
}

const normalizeAction = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_')

const allows = (actions: string[] | undefined, candidates: string[], legacyFallback: boolean) => {
  if (actions === undefined) return legacyFallback
  const allowed = new Set(actions.map(normalizeAction))
  return allowed.has('*')
    || allowed.has('manage')
    || candidates.some((candidate) => allowed.has(normalizeAction(candidate)))
}

const contentSnapshot = (skill: SkillDetail) => JSON.stringify({
  id: skill.id.trim(),
  name: skill.name || skill.id,
  label: skill.label,
  description: skill.description,
  instructions: skill.instructions,
  frontmatter: (() => {
    if (typeof skill.frontmatter_text !== 'string') return JSON.stringify(skill.frontmatter || {})
    try {
      return JSON.stringify(JSON.parse(skill.frontmatter_text))
    } catch {
      return skill.frontmatter_text
    }
  })(),
  resources: [...(skill.resources || [])]
    .sort((left, right) => left.path.localeCompare(right.path))
    .map(({ path, kind, size, sha256, executable }) => ({
      path,
      kind: kind || '',
      size: size || 0,
      sha256: sha256 || '',
      executable: Boolean(executable),
    })),
})

const settingsSnapshot = (skill: SkillDetail) => JSON.stringify({
  tools: skill.tools,
  default: skill.default,
  enabled: skill.enabled,
  visibility: skill.visibility,
  order: skill.order,
  always_on: skill.always_on,
  routable: skill.routable,
  routing_examples: {
    positive: skill.routing_examples.positive || [],
    negative: skill.routing_examples.negative || [],
  },
})

const originLabel = (origin: string | SkillOrigin | undefined) => {
  if (!origin) return '未知来源'
  if (typeof origin === 'string') return origin
  return origin.label || origin.type || origin.source || '标准包'
}

const compatibilityInfo = (compatibility: string | SkillCompatibility | undefined) => {
  if (!compatibility) {
    return {
      label: '未检查',
      reasons: [] as string[],
      formatCompatible: undefined as boolean | undefined,
      runtimeReady: undefined as boolean | undefined,
      ready: undefined as boolean | undefined,
    }
  }
  if (typeof compatibility === 'string') {
    const normalized = compatibility.toLowerCase()
    const compatible = !normalized.includes('incompatible') && !normalized.includes('不兼容')
    return {
      label: compatibility,
      reasons: [] as string[],
      formatCompatible: compatible,
      runtimeReady: undefined as boolean | undefined,
      ready: compatible,
    }
  }
  const reasons = [
    ...(compatibility.reasons || []),
    ...(compatibility.diagnostics || []),
  ]
  const formatCompatible = compatibility.format_compatible
  const runtimeReady = compatibility.runtime_ready
  const ready = formatCompatible === false ? false : runtimeReady === true ? true : undefined
  return {
    label: compatibility.level || compatibility.status || compatibility.summary || '已检查',
    reasons: Array.from(new Set(reasons)),
    formatCompatible,
    runtimeReady,
    ready,
  }
}

const statusTone = (value: string, positive?: boolean) => {
  const normalized = value.toLowerCase()
  if (positive === false || /failed|error|broken|rejected|quarantined|incompatible|失败|错误|不兼容/.test(normalized)) {
    return 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300'
  }
  if (positive === true || /enabled|active|ready|compatible|healthy|完成|启用|兼容/.test(normalized)) {
    return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300'
  }
  return 'border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
}

const versionToken = (version: SkillVersion) => (
  version.version ?? version.revision ?? version.id
)

const versionId = (version: SkillVersion) => String(version.id ?? '')

const revisionNumber = (value: unknown) => {
  const revision = Number(value)
  return Number.isInteger(revision) && revision >= 1 ? revision : 0
}

const formatDate = (value: unknown) => {
  if (typeof value !== 'string' || !value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const frontmatterText = (skill: SkillDetail) => (
  typeof skill.frontmatter_text === 'string'
    ? skill.frontmatter_text
    : JSON.stringify(skill.frontmatter || {}, null, 2)
)

const validateResourcePath = (rawPath: string) => {
  const path = rawPath.trim().normalize('NFC')
  if (!path || path.length > 512) throw new Error('资源路径不能为空且不能超过 512 个字符。')
  if (path === 'SKILL.md' || path.toLowerCase() === 'skill.md') {
    throw new Error('SKILL.md 由结构化编辑器管理，不能作为资源上传。')
  }
  if (path.startsWith('/') || path.startsWith('\\') || /^[a-z]:/i.test(path)) {
    throw new Error(`资源路径必须是 package 内的相对路径：${path}`)
  }
  if (path.includes('\\') || [...path].some((character) => character.charCodeAt(0) < 32)) {
    throw new Error(`资源路径包含不支持的字符：${path}`)
  }
  const segments = path.split('/')
  if (segments.length > 24 || segments.some((segment) => !segment || segment === '.' || segment === '..')) {
    throw new Error(`资源路径包含无效目录层级：${path}`)
  }
  if (segments.some((segment) => segment.length > 255 || segment.includes(':') || segment.endsWith(' ') || segment.endsWith('.'))) {
    throw new Error(`资源路径不符合跨平台命名规则：${path}`)
  }
  return path
}

const resourceKind = (path: string) => {
  const root = path.split('/', 1)[0].toLowerCase()
  if (root === 'scripts') return 'script'
  if (root === 'references') return 'reference'
  if (root === 'assets') return 'asset'
  return 'resource'
}

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return window.btoa(binary)
}

const hashBytes = async (bytes: Uint8Array) => {
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest('SHA-256', Uint8Array.from(bytes).buffer)
    return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
  }
  let hash = 2166136261
  for (const value of bytes) hash = Math.imul(hash ^ value, 16777619)
  return `local-${(hash >>> 0).toString(16).padStart(8, '0')}-${bytes.length}`
}

const readPendingResource = async (file: File, path: string): Promise<PendingResource> => {
  if (file.size > MAX_RESOURCE_BYTES) {
    throw new Error(`资源 ${path} 超过单文件 8 MiB 限制。`)
  }
  const bytes = new Uint8Array(await file.arrayBuffer())
  const kind = resourceKind(path)
  return {
    path,
    kind,
    size: bytes.length,
    sha256: await hashBytes(bytes),
    executable: kind === 'script',
    content_base64: bytesToBase64(bytes),
  }
}

export default function SkillManager() {
  const [skills, setSkills] = useState<ChatSkill[]>([])
  const [tools, setTools] = useState<ChatTool[]>([])
  const [catalogActions, setCatalogActions] = useState<string[] | undefined>()
  const [selectedId, setSelectedId] = useState('')
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<SkillDetail>(() => cloneSkill(emptySkill))
  const [baseline, setBaseline] = useState<SkillDetail>(() => cloneSkill(emptySkill))
  const [activeTab, setActiveTab] = useState<ManagerTab>('content')
  const [loading, setLoading] = useState(false)
  const [operation, setOperation] = useState('')
  const [message, setMessage] = useState('')
  const [toolMenuOpen, setToolMenuOpen] = useState(false)
  const [openToolCategory, setOpenToolCategory] = useState('')
  const [versions, setVersions] = useState<SkillVersion[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [versionsLoadedFor, setVersionsLoadedFor] = useState('')
  const [pendingDraft, setPendingDraft] = useState<PendingDraft | null>(null)
  const [importReview, setImportReview] = useState<SkillImportResult | null>(null)
  const [resourceChanges, setResourceChanges] = useState<ResourceEditState>(emptyResourceChanges)
  const [resourcePath, setResourcePath] = useState('')
  const [resourceTargetPath, setResourceTargetPath] = useState('')
  const importInputRef = useRef<HTMLInputElement>(null)
  const resourceInputRef = useRef<HTMLInputElement>(null)

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.id === selectedId),
    [skills, selectedId],
  )
  const selectedExists = Boolean(selectedSkill)
  const hasEditor = creating || selectedExists
  const contentDirty = hasEditor && contentSnapshot(form) !== contentSnapshot(baseline)
  const settingsDirty = hasEditor && settingsSnapshot(form) !== settingsSnapshot(baseline)
  const isDirty = creating || contentDirty || settingsDirty
  const busy = Boolean(operation)

  const detailActions = form.allowed_actions ?? selectedSkill?.allowed_actions
  const canCreate = allows(catalogActions, ['create', 'create_draft', 'create_skill', 'skill_create'], true)
  const canImport = allows(catalogActions, ['import', 'import_package', 'import_skill', 'skill_import'], true)
  const canEditContent = creating
    ? canCreate
    : allows(detailActions, ['edit', 'update', 'update_draft', 'edit_content', 'update_content', 'skill_update'], true)
  const canPublish = creating
    ? canCreate
    : allows(detailActions, ['publish', 'publish_draft', 'skill_publish'], canEditContent)
  const canEditSettings = creating
    ? canCreate
    : allows(detailActions, ['configure', 'settings', 'update_settings', 'edit_settings', 'skill_settings'], canEditContent)
  const canArchive = !creating && allows(detailActions, ['delete', 'archive', 'uninstall', 'skill_delete'], true)
  const canRollback = !creating && allows(detailActions, ['rollback', 'skill_rollback'], true)
  const canExport = !creating && allows(detailActions, ['export', 'export_version', 'skill_export'], true)
  const canSaveContent = canEditContent && canPublish
  const compatibility = compatibilityInfo(form.compatibility)
  const importCompatibility = compatibilityInfo(importReview?.compatibility)

  const groupedTools = useMemo(() => {
    const groups = new Map<string, ChatTool[]>()
    for (const tool of tools) {
      const category = tool.category || 'general'
      groups.set(category, [...(groups.get(category) || []), tool])
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [tools])

  const selectedToolLabels = useMemo(() => {
    const toolById = new Map(tools.map((tool) => [tool.id, tool]))
    return form.tools.map((toolId) => toolById.get(toolId)?.label || toolId).filter(Boolean)
  }, [form.tools, tools])

  const confirmDiscard = useCallback(() => (
    !isDirty || window.confirm('当前 Skill 有未保存的改动，确定放弃吗？')
  ), [isDirty])

  useEffect(() => {
    if (!isDirty) return undefined
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    const guardLinks = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element) || !target.closest('a[href]')) return
      if (!window.confirm('当前 Skill 有未保存的改动，确定离开吗？')) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    document.addEventListener('click', guardLinks, true)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload)
      document.removeEventListener('click', guardLinks, true)
    }
  }, [isDirty])

  useEffect(() => {
    if (!openToolCategory && groupedTools.length > 0) {
      setOpenToolCategory(groupedTools[0][0])
    }
  }, [groupedTools, openToolCategory])

  const loadCatalog = useCallback(async (nextSelectedId?: string) => {
    let res
    try {
      res = await chatApi.skillCatalog()
    } catch {
      res = await chatApi.skills()
    }
    const catalog = res.data
    setSkills(catalog?.skills || [])
    setTools(catalog?.tools || [])
    setCatalogActions(catalog?.allowed_actions)
    if (nextSelectedId) setSelectedId(nextSelectedId)
    return catalog
  }, [])

  const loadDetail = useCallback(async (skillId: string) => {
    setLoading(true)
    setToolMenuOpen(false)
    try {
      const res = await chatApi.skillDetail(skillId)
      if (res.data) {
        const detail = cloneSkill(res.data)
        setForm(detail)
        setBaseline(cloneSkill(detail))
        setResourceChanges(emptyResourceChanges())
        setResourcePath('')
        setResourceTargetPath('')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const loadVersions = useCallback(async (skillId: string) => {
    setVersionsLoading(true)
    try {
      const res = await chatApi.skillVersions(skillId)
      setVersions(res.data?.versions || [])
      setVersionsLoadedFor(skillId)
    } catch (error) {
      setMessage(errorMessage(error, '加载版本历史失败'))
    } finally {
      setVersionsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(errorMessage(error, '加载 Skill 列表失败')))
  }, [loadCatalog])

  useEffect(() => {
    if (!creating && !selectedId && skills.length > 0) setSelectedId(skills[0].id)
  }, [creating, selectedId, skills])

  useEffect(() => {
    if (creating) {
      setLoading(false)
      return
    }
    if (!selectedId) {
      const empty = cloneSkill(emptySkill)
      setForm(empty)
      setBaseline(cloneSkill(empty))
      setResourceChanges(emptyResourceChanges())
      setResourcePath('')
      setResourceTargetPath('')
      return
    }
    loadDetail(selectedId).catch((error) => setMessage(errorMessage(error, '加载 Skill 详情失败')))
  }, [creating, loadDetail, selectedId])

  useEffect(() => {
    if (activeTab === 'versions' && selectedId && versionsLoadedFor !== selectedId) {
      loadVersions(selectedId).catch(() => undefined)
    }
  }, [activeTab, loadVersions, selectedId, versionsLoadedFor])

  const selectSkill = (skillId: string) => {
    if (skillId === selectedId && !creating) return
    if (!confirmDiscard()) return
    setCreating(false)
    setActiveTab('content')
    setSelectedId(skillId)
    setPendingDraft(null)
    setImportReview(null)
    setResourceChanges(emptyResourceChanges())
    setResourcePath('')
    setResourceTargetPath('')
    setMessage('')
  }

  const startCreate = () => {
    if (!canCreate || !confirmDiscard()) return
    const index = skills.length + 1
    const id = slugifyName(`custom-skill-${index}`, `custom-skill-${index}`)
    const draft = cloneSkill({
      ...emptySkill,
      id,
      label: '新 Skill',
      description: '描述这个 Skill 的用途。',
      instructions: '# 新 Skill\n\n描述这个 Skill 的行为规则。\n',
    })
    setCreating(true)
    setSelectedId('')
    setForm(draft)
    setBaseline(cloneSkill(draft))
    setActiveTab('content')
    setVersions([])
    setVersionsLoadedFor('')
    setPendingDraft(null)
    setImportReview(null)
    setResourceChanges(emptyResourceChanges())
    setResourcePath('')
    setResourceTargetPath('')
    setMessage('')
  }

  const openImport = () => {
    if (!canImport || !confirmDiscard()) return
    importInputRef.current?.click()
  }

  const importPackage = async (file: File | undefined) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setMessage('请选择 ZIP 格式的 Skill package。')
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      setMessage('Skill package 不能超过 50 MiB。')
      return
    }
    setOperation('import')
    setMessage('')
    try {
      const res = await chatApi.importSkill(file)
      const result = res.data
      const importId = result?.import_id || result?.id
      if (!importId) throw new Error('导入响应缺少 import ID')
      setMessage(`Skill package 已上传，正在检查（任务 ${importId}）。`)

      let latest = result
      for (let attempt = 0; attempt < 30; attempt += 1) {
        if (/review_required|awaiting_approval|installed_disabled|enabled|published|rejected|quarantined|failed/i.test(latest?.status || '')) break
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
        latest = (await chatApi.skillImportDetail(importId)).data
      }
      await loadCatalog()
      setVersionsLoadedFor('')
      const importStatus = latest?.status || 'processing'
      const diagnostic = latest?.diagnostics?.[0]
      const diagnosticText = diagnostic
        ? String(diagnostic.message || diagnostic.detail || diagnostic.code || '')
        : ''
      setMessage(
        /rejected|quarantined|failed/i.test(importStatus)
          ? `Skill package 检查失败：${diagnosticText || importStatus}`
          : /review_required|awaiting_approval/i.test(importStatus)
            ? 'Skill package 检查完成，等待管理员审批后安装。'
            : /installed_disabled|enabled/i.test(importStatus)
              ? 'Skill package 已安装；新导入能力默认保持禁用。'
              : `Skill package 检查仍在进行（任务 ${importId}）。`,
      )
      setImportReview(/review_required|awaiting_approval/i.test(importStatus) ? latest : null)
    } catch (error) {
      setMessage(errorMessage(error, '导入 Skill package 失败'))
    } finally {
      setOperation('')
      if (importInputRef.current) importInputRef.current.value = ''
    }
  }

  const approveImport = async () => {
    const importId = importReview?.import_id || importReview?.id
    const digest = importReview?.digest || ''
    if (!importId || !digest) {
      setMessage('检查结果缺少 import ID 或 digest，无法安装。')
      return
    }
    if (compatibilityInfo(importReview.compatibility).formatCompatible === false) {
      setMessage('此 package 格式不兼容，不能安装。')
      return
    }
    setOperation('approve-import')
    setMessage('')
    try {
      const res = await chatApi.approveSkillImport(importId, {
        expected_digest: digest,
        expected_revision: importReview.revision ?? 0,
        enabled: false,
        default: false,
        visibility: 'public',
        order: 100,
        tools: [],
        always_on: false,
        routable: true,
        routing_examples: { positive: [], negative: [] },
      })
      const installedId = res.data?.id
      setImportReview(null)
      await loadCatalog(installedId)
      if (installedId) {
        setCreating(false)
        setSelectedId(installedId)
      }
      setMessage('Skill package 已安装并保持禁用，请完成管理设置后再启用。')
    } catch (error) {
      setMessage(errorMessage(error, '批准安装失败'))
    } finally {
      setOperation('')
    }
  }

  const toggleTool = (toolId: string) => {
    if (!canEditSettings) return
    setForm((current) => ({
      ...current,
      tools: current.tools.includes(toolId)
        ? current.tools.filter((id) => id !== toolId)
        : [...current.tools, toolId],
    }))
  }

  const updateRoutingExamples = (kind: 'positive' | 'negative', value: string) => {
    const examples = value.split('\n').map((item) => item.trim()).filter(Boolean)
    setForm((current) => ({
      ...current,
      routing_examples: { ...current.routing_examples, [kind]: examples },
    }))
  }

  const chooseResource = (targetPath = '') => {
    if (!canSaveContent || busy) return
    setResourceTargetPath(targetPath)
    resourceInputRef.current?.click()
  }

  const uploadResource = async (file: File | undefined) => {
    if (!file) return
    try {
      const requestedPath = resourceTargetPath || resourcePath || file.name
      const path = validateResourcePath(requestedPath)
      const collision = (form.resources || []).find(
        (resource) => resource.path.toLocaleLowerCase() === path.toLocaleLowerCase() && resource.path !== path,
      )
      if (collision) throw new Error(`资源路径与现有文件冲突：${collision.path}`)

      const pending = await readPendingResource(file, path)
      const nextResources = [
        ...(form.resources || []).filter((resource) => resource.path !== path),
        pending,
      ].sort((left, right) => left.path.localeCompare(right.path))
      if (nextResources.length > MAX_RESOURCE_FILES) {
        throw new Error(`资源文件不能超过 ${MAX_RESOURCE_FILES} 个。`)
      }
      const totalBytes = nextResources.reduce((total, resource) => total + Number(resource.size || 0), 0)
      if (totalBytes > MAX_RESOURCE_TOTAL_BYTES) {
        throw new Error('资源总大小不能超过 32 MiB。')
      }

      setForm((current) => ({ ...current, resources: nextResources }))
      setResourceChanges((current) => ({
        upsert: [...current.upsert.filter((resource) => resource.path !== path), pending],
        delete: current.delete.filter((deletedPath) => deletedPath !== path),
      }))
      setResourcePath('')
      setMessage(`${path} 已加入待保存资源。`)
    } catch (error) {
      setMessage(errorMessage(error, '读取资源失败'))
    } finally {
      setResourceTargetPath('')
      if (resourceInputRef.current) resourceInputRef.current.value = ''
    }
  }

  const removeResource = (path: string) => {
    if (!canSaveContent || busy) return
    const persistedResources = pendingDraft?.resources || baseline.resources || []
    const persisted = persistedResources.some((resource) => resource.path === path)
    setForm((current) => ({
      ...current,
      resources: (current.resources || []).filter((resource) => resource.path !== path),
    }))
    setResourceChanges((current) => ({
      upsert: current.upsert.filter((resource) => resource.path !== path),
      delete: persisted
        ? Array.from(new Set([...current.delete, path]))
        : current.delete.filter((deletedPath) => deletedPath !== path),
    }))
    setMessage(`${path} 将在保存后删除。`)
  }

  const undoResourceChange = (path: string) => {
    if (!canSaveContent || busy) return
    const persistedResources = pendingDraft?.resources || baseline.resources || []
    const original = persistedResources.find((resource) => resource.path === path)
    setForm((current) => ({
      ...current,
      resources: original
        ? [...(current.resources || []).filter((resource) => resource.path !== path), { ...original }]
          .sort((left, right) => left.path.localeCompare(right.path))
        : (current.resources || []).filter((resource) => resource.path !== path),
    }))
    setResourceChanges((current) => ({
      upsert: current.upsert.filter((resource) => resource.path !== path),
      delete: current.delete.filter((deletedPath) => deletedPath !== path),
    }))
    setMessage(`${path} 的资源改动已撤销。`)
  }

  const buildResourceChanges = (): SkillResourceChanges | undefined => {
    const changes = {
      upsert: resourceChanges.upsert
        .map(({ path, content_base64 }) => ({ path, content_base64 }))
        .sort((left, right) => left.path.localeCompare(right.path)),
      delete: [...resourceChanges.delete].sort((left, right) => left.localeCompare(right)),
    }
    return changes.upsert.length > 0 || changes.delete.length > 0 ? changes : undefined
  }

  const buildDraftPayload = () => ({
    name: String(form.name || form.id).trim(),
    display_name: form.label.trim(),
    description: form.description.trim(),
    instructions: form.instructions,
    frontmatter: (() => {
      if (typeof form.frontmatter_text !== 'string') return form.frontmatter || {}
      try {
        const parsed = JSON.parse(form.frontmatter_text)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('frontmatter 必须是 JSON 对象')
        }
        return parsed as Record<string, unknown>
      } catch (error) {
        throw new Error(`frontmatter JSON 无效：${errorMessage(error, '解析失败')}`, { cause: error })
      }
    })(),
  })

  const buildSettingsPayload = (expectedRevision: number): SkillSettingsPayload => ({
    enabled: form.enabled,
    default: form.default,
    visibility: form.visibility,
    order: form.order,
    tools: [...form.tools],
    always_on: form.always_on,
    routable: form.routable,
    routing_examples: {
      positive: form.routing_examples.positive || [],
      negative: form.routing_examples.negative || [],
    },
    expected_revision: expectedRevision,
  })

  const save = async () => {
    if (!String(form.name || form.id).trim() || !form.label.trim() || !form.description.trim()) {
      setMessage('标准名称、显示名称和描述不能为空。')
      return
    }
    if ((!creating && contentDirty && !canSaveContent) || (!creating && settingsDirty && !canEditSettings)) {
      setMessage('当前账号没有保存这些改动的权限。')
      return
    }
    setOperation('save')
    setMessage('')
    let savedDraft: PendingDraft | null = null
    let published = false
    try {
      const snapshot = contentSnapshot(form)
      if (creating || contentDirty) {
        if (pendingDraft?.snapshot === snapshot) {
          savedDraft = pendingDraft
        } else {
          const currentRevision = pendingDraft?.revision || revisionNumber(form.revision)
          const draftPayload = buildDraftPayload()
          const changedResources = buildResourceChanges()
          const res = creating && !pendingDraft
            ? await chatApi.createSkillDraft({
              ...draftPayload,
              resources: resourceChanges.upsert
                .map(({ path, content_base64 }) => ({ path, content_base64 }))
                .sort((left, right) => left.path.localeCompare(right.path)),
            })
            : await chatApi.updateSkillDraft(
              pendingDraft?.id || selectedId,
              {
                ...draftPayload,
                ...(changedResources ? { resource_changes: changedResources } : {}),
                expected_revision: currentRevision,
              },
            )
          const draftId = res.data?.id || pendingDraft?.id || selectedId
          const draftRevision = revisionNumber(res.data?.revision)
          if (!draftId || !draftRevision) throw new Error('draft 响应缺少 Skill ID 或 revision')
          savedDraft = {
            id: draftId,
            revision: draftRevision,
            snapshot,
            resources: (form.resources || []).map((resource) => ({ ...resource })),
          }
          setPendingDraft(savedDraft)
          setResourceChanges(emptyResourceChanges())
        }

        const publishRes = await chatApi.publishSkill(
          savedDraft.id,
          buildSettingsPayload(savedDraft.revision),
        )
        published = true
        const publishedId = publishRes.data?.id || savedDraft.id
        setCreating(false)
        setPendingDraft(null)
        setSelectedId(publishedId)
        await loadCatalog(publishedId)
        await loadDetail(publishedId)
        setVersionsLoadedFor('')
        setMessage(creating ? 'Skill 已创建并发布。' : 'Skill 新版本已发布。')
      } else {
        if (!settingsDirty) {
          setMessage('没有需要保存的改动。')
          return
        }
        const revision = revisionNumber(form.revision)
        if (!revision) throw new Error('Skill 详情缺少有效 revision，请刷新后重试')
        await chatApi.updateSkillSettings(selectedId, buildSettingsPayload(revision))
        await loadCatalog(selectedId)
        await loadDetail(selectedId)
        setVersionsLoadedFor('')
        setMessage('Skill 管理设置已保存。')
      }
    } catch (error) {
      if (published) {
        setMessage(`Skill 已发布，但刷新页面数据失败：${errorMessage(error, '未知错误')}`)
      } else if (savedDraft) {
        setMessage(`draft 已保存，但发布失败；可直接重试：${errorMessage(error, '未知错误')}`)
      } else {
        setMessage(errorMessage(error, '保存失败'))
      }
    } finally {
      setOperation('')
    }
  }

  const archiveSkill = async () => {
    if (!selectedExists || !selectedId || !canArchive || !confirmDiscard()) return
    const revision = revisionNumber(form.revision)
    if (!revision) {
      setMessage('Skill 详情缺少有效 revision，请刷新后重试。')
      return
    }
    if (!window.confirm(`归档 Skill「${form.label || selectedId}」？`)) return
    setOperation('archive')
    setMessage('')
    try {
      await chatApi.deleteSkill(selectedId, revision)
      setCreating(false)
      setSelectedId('')
      const empty = cloneSkill(emptySkill)
      setForm(empty)
      setBaseline(cloneSkill(empty))
      setVersions([])
      setVersionsLoadedFor('')
      setPendingDraft(null)
      setImportReview(null)
      setResourceChanges(emptyResourceChanges())
      setResourcePath('')
      setResourceTargetPath('')
      await loadCatalog()
      setMessage('Skill 已归档。')
    } catch (error) {
      setMessage(errorMessage(error, '归档失败'))
    } finally {
      setOperation('')
    }
  }

  const rollback = async (version: SkillVersion) => {
    const token = versionToken(version)
    const targetVersionId = versionId(version)
    const revision = revisionNumber(form.revision)
    if (!selectedId || !targetVersionId || token === undefined || !canRollback || !confirmDiscard()) return
    if (!revision) {
      setMessage('Skill 详情缺少有效 revision，请刷新后重试。')
      return
    }
    if (!window.confirm(`将「${form.label || selectedId}」回滚到版本 ${String(token)}？`)) return
    setOperation('rollback')
    setMessage('')
    try {
      await chatApi.rollbackSkill(selectedId, targetVersionId, revision)
      await loadCatalog(selectedId)
      await loadDetail(selectedId)
      await loadVersions(selectedId)
      setMessage(`Skill 已回滚到版本 ${String(token)}。`)
    } catch (error) {
      setMessage(errorMessage(error, '回滚失败，当前有效版本保持不变'))
    } finally {
      setOperation('')
    }
  }

  const exportPackage = async () => {
    if (!selectedId || !canExport) return
    setOperation('export')
    setMessage('')
    try {
      let currentVersionId = form.version_id || ''
      if (!currentVersionId) {
        const res = await chatApi.skillVersions(selectedId)
        const activeVersion = res.data?.versions.find((version) => (
          version.active
          || version.is_active
          || String(version.version) === String(form.version)
        ))
        currentVersionId = activeVersion ? versionId(activeVersion) : ''
      }
      if (!currentVersionId) throw new Error('未找到当前可导出的版本')
      const { blob, filename } = await chatApi.exportSkill(selectedId, currentVersionId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setMessage('Skill package 已导出。')
    } catch (error) {
      setMessage(errorMessage(error, '导出失败'))
    } finally {
      setOperation('')
    }
  }

  return (
    <div className="h-full min-h-0 flex flex-col lg:flex-row bg-[var(--color-bg)]">
      <aside className="w-full lg:w-72 shrink-0 border-b lg:border-b-0 lg:border-r border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-4 max-h-64 lg:max-h-none overflow-y-auto">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-heading text-lg text-[var(--color-text)]">Skill</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">标准 package 与本地能力</p>
          </div>
          <div className="flex items-center gap-1">
            {canImport && (
              <button
                type="button"
                onClick={openImport}
                disabled={busy}
                className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-50"
                title="导入本地 ZIP"
              >
                <Upload size={15} />
              </button>
            )}
            {canCreate && (
              <button
                type="button"
                onClick={startCreate}
                disabled={busy}
                className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-50"
                title="新增 Skill"
              >
                <Plus size={16} />
              </button>
            )}
            <input
              ref={importInputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(event) => importPackage(event.target.files?.[0])}
            />
          </div>
        </div>

        <div className="space-y-1">
          {skills.map((skill) => {
            const skillCompatibility = compatibilityInfo(skill.compatibility)
            return (
              <button
                key={skill.id}
                type="button"
                onClick={() => selectSkill(skill.id)}
                className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                  selectedId === skill.id && !creating
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                    : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]'
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{skill.label}</span>
                  <span className={`h-2 w-2 shrink-0 rounded-full ${skill.enabled === false ? 'bg-gray-400' : 'bg-emerald-500'}`} />
                </span>
                <span className="mt-1 flex min-w-0 items-center gap-2 text-[11px] opacity-80">
                  <span className="truncate">{originLabel(skill.origin)}</span>
                  {skill.version !== undefined && <span className="shrink-0">v{String(skill.version)}</span>}
                  {skillCompatibility.formatCompatible === false && <span className="shrink-0 text-[var(--color-danger)]">不兼容</span>}
                  {skillCompatibility.formatCompatible !== false && skillCompatibility.runtimeReady === false && (
                    <span className="shrink-0 text-amber-600 dark:text-amber-300">保持禁用</span>
                  )}
                </span>
              </button>
            )
          })}
          {skills.length === 0 && (
            <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">
              暂无 Skill。
            </div>
          )}
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {importReview && (
          <section className="mx-auto mb-5 max-w-5xl border-l-2 border-[var(--color-accent)] bg-[var(--color-card)] px-4 py-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Package size={16} className="text-[var(--color-accent)]" />
                  <span className="font-medium text-sm text-[var(--color-text)]">{importReview.name || '待安装 Skill package'}</span>
                  <span className={`rounded border px-2 py-0.5 text-xs ${statusTone(importCompatibility.label, importCompatibility.ready)}`}>
                    {importCompatibility.label}
                  </span>
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-secondary)]">
                  摘要：{importReview.digest?.slice(0, 16) || '等待生成'}
                </div>
                {importCompatibility.reasons.map((reason) => (
                  <div key={reason} className="mt-1 text-xs text-[var(--color-danger)]">{reason}</div>
                ))}
                {importCompatibility.formatCompatible !== false && importCompatibility.runtimeReady === false && (
                  <div className="mt-1 text-xs text-amber-600 dark:text-amber-300">
                    可安装和管理，但在隔离运行时就绪前会保持禁用。
                  </div>
                )}
              </div>
              {canImport && (
                <button
                  type="button"
                  onClick={approveImport}
                  disabled={busy || importCompatibility.formatCompatible === false || !importReview.digest}
                  className="h-9 shrink-0 inline-flex items-center justify-center gap-2 rounded-md bg-[var(--color-accent)] px-3 text-sm text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ShieldCheck size={15} />
                  {operation === 'approve-import' ? '安装中' : '批准并安装'}
                </button>
              )}
            </div>
          </section>
        )}
        {!hasEditor ? (
          <div className="mx-auto flex min-h-72 max-w-xl flex-col items-center justify-center text-center text-[var(--color-text-secondary)]">
            <Package size={30} className="mb-3" />
            <p className="text-sm">选择一个 Skill，或新建、导入标准 package。</p>
          </div>
        ) : (
          <div className="mx-auto max-w-5xl space-y-5">
            <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-heading text-xl text-[var(--color-text)] break-words">
                    {form.label || form.id || '新增 Skill'}
                  </h2>
                  {form.status && (
                    <span className={`rounded border px-2 py-0.5 text-xs ${statusTone(form.status)}`}>{form.status}</span>
                  )}
                  <span className={`rounded border px-2 py-0.5 text-xs ${statusTone(compatibility.label, compatibility.ready)}`}>
                    {compatibility.label}
                  </span>
                  {isDirty && <span className="text-xs text-amber-600 dark:text-amber-300">未保存</span>}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-text-secondary)]">
                  <span>来源：{originLabel(form.origin)}</span>
                  <span>版本：{String(form.version ?? form.revision ?? '草稿')}</span>
                  {selectedExists && <span title={form.id}>内部 ID：{form.id.slice(0, 12)}</span>}
                  {form.license && <span>许可证：{form.license}</span>}
                  {form.digest && <span title={form.digest}>摘要：{form.digest.slice(0, 12)}</span>}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {canExport && selectedExists && (
                  <button type="button" onClick={exportPackage} disabled={busy} className={secondaryButtonClass}>
                    <Download size={15} />
                    导出
                  </button>
                )}
                {canArchive && selectedExists && (
                  <button type="button" onClick={archiveSkill} disabled={busy} className={`${secondaryButtonClass} text-[var(--color-danger)]`}>
                    <Archive size={15} />
                    归档
                  </button>
                )}
                {(creating ? canCreate : canSaveContent || canEditSettings) && (
                  <button
                    type="button"
                    onClick={save}
                    disabled={busy || loading || (!creating && !contentDirty && !settingsDirty)}
                    className="h-9 inline-flex items-center justify-center gap-2 px-3 rounded-md bg-[var(--color-accent)] text-sm text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Save size={15} />
                    {operation === 'save' ? '保存中' : '保存'}
                  </button>
                )}
              </div>
            </header>

            {message && (
              <div role="status" className="rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 text-sm text-[var(--color-text-secondary)]">
                {message}
              </div>
            )}

            {compatibility.reasons.length > 0 && (
              <section className="border-l-2 border-amber-400 pl-3 text-sm text-[var(--color-text-secondary)]">
                <div className="font-medium text-[var(--color-text)]">兼容性诊断</div>
                {compatibility.reasons.map((reason) => <div key={reason}>{reason}</div>)}
              </section>
            )}

            <nav className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)]" aria-label="Skill 详情">
              {([
                ['content', '内容', FileText],
                ['settings', '管理设置', Settings2],
                ['versions', '版本', History],
              ] as const).map(([tab, label, Icon]) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  disabled={creating && tab === 'versions'}
                  className={`h-10 shrink-0 inline-flex items-center gap-2 px-3 border-b-2 text-sm disabled:opacity-40 ${
                    activeTab === tab
                      ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                      : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
                  }`}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </nav>

            {loading ? (
              <div className="py-16 text-center text-sm text-[var(--color-text-secondary)]">正在加载 Skill...</div>
            ) : activeTab === 'content' ? (
              <div className="space-y-5">
                <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">标准名称</span>
                    <input
                      value={form.name || form.id}
                      onChange={(event) => setForm((current) => ({
                        ...current,
                        name: event.target.value,
                        id: creating ? event.target.value : current.id,
                      }))}
                      disabled={selectedExists || !canSaveContent}
                      className={inputClass}
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">名称</span>
                    <input
                      value={form.label}
                      onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
                      disabled={!canSaveContent}
                      className={inputClass}
                    />
                  </label>
                  <label className="space-y-1 sm:col-span-2">
                    <span className="text-xs text-[var(--color-text-secondary)]">描述</span>
                    <input
                      value={form.description}
                      onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                      disabled={!canSaveContent}
                      className={inputClass}
                    />
                  </label>
                </section>

                <section className="space-y-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-[var(--color-text-secondary)]">SKILL.md 执行指令</span>
                    {selectedExists && <span className="text-xs text-[var(--color-text-secondary)]">保存后生成新版本</span>}
                  </div>
                  <textarea
                    value={form.instructions}
                    onChange={(event) => setForm((current) => ({ ...current, instructions: event.target.value }))}
                    disabled={!canSaveContent}
                    rows={20}
                    className={`${inputClass} px-3 py-2 font-mono resize-y`}
                  />
                </section>

                <section className="grid grid-cols-1 gap-5 border-t border-[var(--color-border)] pt-5 lg:grid-cols-2">
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">扩展 frontmatter（JSON）</span>
                    <textarea
                      value={frontmatterText(form)}
                      onChange={(event) => setForm((current) => ({ ...current, frontmatter_text: event.target.value }))}
                      disabled={!canSaveContent}
                      rows={10}
                      spellCheck={false}
                      className={`${inputClass} px-3 py-2 font-mono resize-y`}
                    />
                  </label>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs text-[var(--color-text-secondary)]">Package 资源</div>
                      <span className="text-xs text-[var(--color-text-secondary)]">
                        {(form.resources || []).length} / {MAX_RESOURCE_FILES}
                      </span>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        value={resourcePath}
                        onChange={(event) => setResourcePath(event.target.value)}
                        disabled={!canSaveContent || busy}
                        placeholder="资源路径（留空使用文件名）"
                        aria-label="资源路径"
                        className={inputClass}
                      />
                      <button
                        type="button"
                        onClick={() => chooseResource()}
                        disabled={!canSaveContent || busy}
                        className={`${secondaryButtonClass} shrink-0`}
                      >
                        <Upload size={15} />
                        上传
                      </button>
                      <input
                        ref={resourceInputRef}
                        type="file"
                        className="hidden"
                        aria-label="选择 Skill 资源文件"
                        onChange={(event) => uploadResource(event.target.files?.[0])}
                      />
                    </div>
                    {(form.resources || []).length === 0 ? (
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-8 text-center text-sm text-[var(--color-text-secondary)]">
                        此版本没有附加资源。
                      </div>
                    ) : (
                      <div className="max-h-64 divide-y divide-[var(--color-border)] overflow-y-auto border-y border-[var(--color-border)]">
                        {(form.resources || []).map((resource) => (
                          <div key={resource.path} className="flex items-start justify-between gap-3 py-2 text-sm">
                            <span className="min-w-0">
                              <span className="block truncate text-[var(--color-text)]" title={resource.path}>{resource.path}</span>
                              <span className="block text-xs text-[var(--color-text-secondary)]">
                                {resource.kind || 'file'}{resource.size ? ` · ${resource.size} B` : ''}
                                {resourceChanges.upsert.some((item) => item.path === resource.path) && (
                                  <span className="ml-2 text-amber-600 dark:text-amber-300">
                                    {(baseline.resources || []).some((item) => item.path === resource.path) ? '待替换' : '待新增'}
                                  </span>
                                )}
                              </span>
                            </span>
                            <span className="flex shrink-0 items-center gap-1">
                              {resourceChanges.upsert.some((item) => item.path === resource.path) && (
                                <button
                                  type="button"
                                  onClick={() => undoResourceChange(resource.path)}
                                  disabled={!canSaveContent || busy}
                                  className="h-8 w-8 inline-flex items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-accent)] disabled:opacity-50"
                                  title={`撤销 ${resource.path} 的改动`}
                                >
                                  <Undo2 size={14} />
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => chooseResource(resource.path)}
                                disabled={!canSaveContent || busy}
                                className="h-8 w-8 inline-flex items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-accent)] disabled:opacity-50"
                                title={`替换 ${resource.path}`}
                              >
                                <Upload size={14} />
                              </button>
                              <button
                                type="button"
                                onClick={() => removeResource(resource.path)}
                                disabled={!canSaveContent || busy}
                                className="h-8 w-8 inline-flex items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-red-50 hover:text-[var(--color-danger)] disabled:opacity-50 dark:hover:bg-red-950/30"
                                title={`删除 ${resource.path}`}
                              >
                                <Trash2 size={14} />
                              </button>
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {resourceChanges.delete.length > 0 && (
                      <div className="divide-y divide-[var(--color-border)] border-y border-[var(--color-border)]">
                        {resourceChanges.delete.map((path) => (
                          <div key={path} className="flex min-h-10 items-center justify-between gap-3 py-1 text-sm">
                            <span className="min-w-0 truncate text-[var(--color-danger)]" title={path}>{path} · 待删除</span>
                            <button
                              type="button"
                              onClick={() => undoResourceChange(path)}
                              disabled={!canSaveContent || busy}
                              className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-accent)] disabled:opacity-50"
                              title={`撤销删除 ${path}`}
                            >
                              <Undo2 size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="text-xs text-[var(--color-text-secondary)]">
                      单文件最多 8 MiB；scripts/ 下文件只会作为禁用的 C 级资源保存。
                    </div>
                  </div>
                </section>
              </div>
            ) : activeTab === 'settings' ? (
              <div className="space-y-6">
                <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <label className="flex min-h-10 items-center gap-3 text-sm text-[var(--color-text)]">
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                      disabled={!canEditSettings || compatibility.runtimeReady === false}
                    />
                    已启用
                  </label>
                  <label className="flex min-h-10 items-center gap-3 text-sm text-[var(--color-text)]">
                    <input
                      type="checkbox"
                      checked={form.default}
                      onChange={(event) => setForm((current) => ({ ...current, default: event.target.checked }))}
                      disabled={!canEditSettings}
                    />
                    默认选择
                  </label>
                  <label className="flex min-h-10 items-center gap-3 text-sm text-[var(--color-text)]">
                    <input
                      type="checkbox"
                      checked={form.routable}
                      onChange={(event) => setForm((current) => ({ ...current, routable: event.target.checked }))}
                      disabled={!canEditSettings}
                    />
                    参与意图路由
                  </label>
                  <label className="flex min-h-10 items-center gap-3 text-sm text-[var(--color-text)]">
                    <input
                      type="checkbox"
                      checked={form.always_on}
                      onChange={(event) => setForm((current) => ({ ...current, always_on: event.target.checked }))}
                      disabled={!canEditSettings}
                    />
                    选中后常驻
                  </label>
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">可见性</span>
                    <select
                      value={form.visibility}
                      onChange={(event) => setForm((current) => ({ ...current, visibility: event.target.value }))}
                      disabled={!canEditSettings}
                      className={inputClass}
                    >
                      <option value="public">公开</option>
                      <option value="private">仅自己</option>
                    </select>
                  </label>
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">排序</span>
                    <input
                      type="number"
                      value={form.order}
                      onChange={(event) => setForm((current) => ({ ...current, order: Number(event.target.value) }))}
                      disabled={!canEditSettings}
                      className={inputClass}
                    />
                  </label>
                </section>

                <section className="space-y-2 border-t border-[var(--color-border)] pt-5">
                  <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text)]">
                    <Wrench size={16} />
                    Tool / MCP 映射
                  </div>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setToolMenuOpen((value) => !value)}
                      disabled={!canEditSettings}
                      className={`${inputClass} px-3 py-2 text-left hover:border-[var(--color-accent)]`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="truncate">{selectedToolLabels.length > 0 ? selectedToolLabels.join(' / ') : '选择工具'}</span>
                        <span className="shrink-0 text-xs text-[var(--color-text-secondary)]">{form.tools.length} / {tools.length}</span>
                      </span>
                    </button>

                    {toolMenuOpen && (
                      <div className="absolute left-0 top-12 z-30 grid w-full max-w-3xl grid-cols-1 overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-card)] shadow-lg sm:grid-cols-[220px_1fr]">
                        <div className="max-h-72 overflow-y-auto border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2 sm:border-b-0 sm:border-r">
                          {groupedTools.map(([category, items]) => {
                            const selectedCount = items.filter((tool) => form.tools.includes(tool.id)).length
                            const active = openToolCategory === category
                            return (
                              <button
                                key={category}
                                type="button"
                                onClick={() => setOpenToolCategory(category)}
                                className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm ${
                                  active
                                    ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg)] hover:text-[var(--color-text)]'
                                }`}
                              >
                                <span className="truncate">{category}</span>
                                <span className="inline-flex items-center gap-1 text-xs">
                                  {selectedCount > 0 ? `${selectedCount}/${items.length}` : items.length}
                                  <ChevronRight size={13} />
                                </span>
                              </button>
                            )
                          })}
                        </div>
                        <div className="max-h-72 overflow-y-auto p-2">
                          {(groupedTools.find(([category]) => category === openToolCategory)?.[1] || []).map((tool) => {
                            const active = form.tools.includes(tool.id)
                            return (
                              <button
                                key={tool.id}
                                type="button"
                                onClick={() => toggleTool(tool.id)}
                                title={tool.description}
                                className={`mb-1 flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left ${
                                  active
                                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                                    : 'border-transparent text-[var(--color-text)] hover:border-[var(--color-border)] hover:bg-[var(--color-bg-secondary)]'
                                }`}
                              >
                                <span className={`mt-0.5 h-4 w-4 shrink-0 rounded border ${active ? 'border-[var(--color-accent)] bg-[var(--color-accent)]' : 'border-[var(--color-border)]'}`} />
                                <span className="min-w-0">
                                  <span className="block text-sm font-medium">
                                    {tool.label} <span className="text-[11px] text-[var(--color-text-secondary)]">[{tool.source === 'mcp' ? 'MCP' : '本地'}]</span>
                                  </span>
                                  <span className="block truncate text-xs text-[var(--color-text-secondary)]">
                                    {tool.provider_id ? `${tool.provider_id} / ${tool.external_name || tool.id}` : tool.description}
                                  </span>
                                </span>
                              </button>
                            )
                          })}
                          {tools.length === 0 && <div className="px-3 py-6 text-sm text-[var(--color-text-secondary)]">暂无可映射工具。</div>}
                        </div>
                      </div>
                    )}
                  </div>
                </section>

                <section className="grid grid-cols-1 gap-4 border-t border-[var(--color-border)] pt-5 lg:grid-cols-2">
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">正向路由样例（每行一条）</span>
                    <textarea
                      value={(form.routing_examples.positive || []).join('\n')}
                      onChange={(event) => updateRoutingExamples('positive', event.target.value)}
                      disabled={!canEditSettings}
                      rows={7}
                      className={`${inputClass} px-3 py-2 resize-y`}
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">负向路由样例（每行一条）</span>
                    <textarea
                      value={(form.routing_examples.negative || []).join('\n')}
                      onChange={(event) => updateRoutingExamples('negative', event.target.value)}
                      disabled={!canEditSettings}
                      rows={7}
                      className={`${inputClass} px-3 py-2 resize-y`}
                    />
                  </label>
                </section>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text)]">
                    <History size={16} />
                    不可变版本历史
                  </div>
                  <button
                    type="button"
                    onClick={() => selectedId && loadVersions(selectedId)}
                    disabled={versionsLoading || busy}
                    className={secondaryButtonClass}
                  >
                    <RefreshCw size={15} className={versionsLoading ? 'animate-spin' : ''} />
                    刷新
                  </button>
                </div>

                {versionsLoading && versions.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-secondary)]">正在加载版本...</div>
                ) : versions.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-secondary)]">暂无版本记录。</div>
                ) : (
                  <div className="divide-y divide-[var(--color-border)] border-y border-[var(--color-border)]">
                    {versions.map((version, index) => {
                      const token = versionToken(version)
                      const active = Boolean(version.active ?? version.is_active)
                        || String(token) === String(form.version ?? form.revision)
                      const versionStatus = version.status || (active ? 'active' : 'available')
                      return (
                        <div key={String(version.id ?? token ?? index)} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-sm text-[var(--color-text)]">版本 {String(token ?? index + 1)}</span>
                              <span className={`rounded border px-2 py-0.5 text-xs ${statusTone(versionStatus, version.healthy === false ? false : undefined)}`}>
                                {versionStatus}
                              </span>
                              {active && (
                                <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-300">
                                  <CheckCircle2 size={13} /> 当前
                                </span>
                              )}
                            </div>
                            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-text-secondary)]">
                              <span>{originLabel(version.origin)}</span>
                              {version.digest && <span title={version.digest}>摘要 {version.digest.slice(0, 12)}</span>}
                              {version.created_at && <span>{formatDate(version.created_at)}</span>}
                              {version.created_by && <span>由 {version.created_by}</span>}
                            </div>
                          </div>
                          {canRollback && !active && token !== undefined && (
                            <button
                              type="button"
                              onClick={() => rollback(version)}
                              disabled={busy || version.healthy === false}
                              className={secondaryButtonClass}
                              title={version.healthy === false ? '该版本未通过健康检查' : '回滚到此版本'}
                            >
                              <RotateCcw size={15} />
                              回滚
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                <section className="grid grid-cols-1 gap-3 border-t border-[var(--color-border)] pt-5 sm:grid-cols-3">
                  <div className="flex items-start gap-2 text-sm text-[var(--color-text-secondary)]">
                    <FileArchive size={16} className="mt-0.5 shrink-0" />
                    <span>每次内容保存生成一个不可变版本。</span>
                  </div>
                  <div className="flex items-start gap-2 text-sm text-[var(--color-text-secondary)]">
                    <ShieldCheck size={16} className="mt-0.5 shrink-0" />
                    <span>回滚失败时保留当前有效版本。</span>
                  </div>
                  <div className="flex items-start gap-2 text-sm text-[var(--color-text-secondary)]">
                    <Download size={16} className="mt-0.5 shrink-0" />
                    <span>导出内容不包含 Doki 管理设置。</span>
                  </div>
                </section>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
