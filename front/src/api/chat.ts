import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse } from '../types/api'

export interface ChatPromptMode {
  value: string
  label: string
}

export interface ChatTool {
  id: string
  label: string
  description: string
  category: string
  order?: number
  is_default?: boolean
  visibility?: string
  risk_level?: 'low' | 'medium' | 'high'
  requires_confirmation?: boolean
  timeout_seconds?: number
  max_output_chars?: number
  source?: 'local' | 'mcp'
  provider_id?: string | null
  external_name?: string | null
  enabled?: boolean
  read_only?: boolean
  server_status?: 'enabled' | 'disabled' | 'offline' | 'error'
  last_error?: string | null
}

export interface ChatSkill {
  id: string
  label: string
  description: string
  tool_ids: string[]
  is_default: boolean
  enabled?: boolean
  status?: string
  origin?: string | SkillOrigin
  version?: string | number
  compatibility?: string | SkillCompatibility
  visibility?: string
  order?: number
  always_on?: boolean
  routable?: boolean
  routing_examples?: Record<string, string[]>
  allowed_actions?: string[]
  [key: string]: unknown
}

export interface ChatSkillCatalog {
  skills: ChatSkill[]
  tools: ChatTool[]
  default_skill_ids: string[]
  default_tool_ids: string[]
  allowed_actions?: string[]
  [key: string]: unknown
}

export interface SkillOrigin {
  type?: string
  source?: string
  label?: string
  author?: string
  url?: string
  commit?: string
  license?: string
  digest?: string
  [key: string]: unknown
}

export interface SkillCompatibility {
  level?: string
  status?: string
  summary?: string
  format_compatible?: boolean
  runtime_ready?: boolean
  reasons?: string[]
  diagnostics?: string[]
  [key: string]: unknown
}

export interface SkillResource {
  path: string
  kind?: string
  size?: number
  sha256?: string
  executable?: boolean
  [key: string]: unknown
}

export interface SkillResourceInput {
  path: string
  content_base64: string
}

export interface SkillResourceChanges {
  upsert: SkillResourceInput[]
  delete: string[]
}

export interface SkillDetail {
  id: string
  name?: string
  label: string
  description: string
  tools: string[]
  default: boolean
  enabled: boolean
  visibility: string
  order: number
  instructions: string
  frontmatter?: Record<string, unknown>
  resources?: SkillResource[]
  always_on: boolean
  routable: boolean
  routing_examples: Record<string, string[]>
  status?: string
  origin?: string | SkillOrigin
  version?: string | number
  version_id?: string
  revision?: string | number
  digest?: string
  compatibility?: string | SkillCompatibility
  allowed_actions?: string[]
  license?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface SkillSettingsPayload {
  enabled: boolean
  default: boolean
  visibility: string
  order: number
  tools: string[]
  always_on: boolean
  routable: boolean
  routing_examples: Record<string, string[]>
  expected_revision: number
}

export interface SkillDraftPayload {
  name: string
  display_name: string
  description: string
  instructions: string
  frontmatter?: Record<string, unknown>
  version_note?: string
}

export interface SkillDraftCreatePayload extends SkillDraftPayload {
  resources?: SkillResourceInput[]
}

export interface SkillDraftUpdatePayload extends SkillDraftPayload {
  resource_changes?: SkillResourceChanges
  expected_revision: number
}

export type SkillPublishPayload = SkillSettingsPayload

export interface SkillVersion {
  id?: string
  version?: string | number
  revision?: string | number
  upstream_version?: string | null
  digest?: string
  status?: string
  origin?: string | SkillOrigin
  created_at?: string
  created_by?: string
  active?: boolean
  is_active?: boolean
  healthy?: boolean
  [key: string]: unknown
}

export interface SkillVersionsResponse {
  versions: SkillVersion[]
  [key: string]: unknown
}

export interface SkillImportResult {
  id?: string
  skill_id?: string
  import_id?: string
  status?: string
  name?: string
  digest?: string
  revision?: number
  compatibility?: SkillCompatibility
  diagnostics?: Array<Record<string, unknown>>
  skill?: Partial<SkillDetail>
  [key: string]: unknown
}

export interface ToolDetail {
  id: string
  label: string
  description: string
  category: string
  order: number
  instructions: string
  entrypoint?: string
  default?: boolean
  visibility?: string
  risk_level?: 'low' | 'medium' | 'high'
  requires_confirmation?: boolean
  timeout_seconds?: number
  max_output_chars?: number
  source?: 'local' | 'mcp'
  provider_id?: string | null
  external_name?: string | null
  enabled?: boolean
  read_only?: boolean
  server_status?: 'enabled' | 'disabled' | 'offline' | 'error'
  last_error?: string | null
}

export interface ToolCatalog {
  tools: ToolDetail[]
}

export interface McpServer {
  id: string
  label: string
  description?: string
  enabled: boolean
  transport: string
  url?: string | null
  command?: string | null
  allow_tools?: string[]
  deny_tools?: string[]
  default_risk_level?: 'low' | 'medium' | 'high'
  default_requires_confirmation?: boolean
  timeout_seconds?: number
  max_output_chars?: number
  status?: 'enabled' | 'disabled' | 'offline' | 'error'
  last_error?: string | null
}

export interface McpServerCatalog {
  servers: McpServer[]
}

export interface McpPermissions {
  can_manage_mcp: boolean
}

export interface McpServerUpdatePayload {
  enabled?: boolean
  label?: string
  description?: string
  url?: string
}

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' ? value as Record<string, unknown> : {}
)

const asStringArray = (value: unknown): string[] => (
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
)

const asRoutingExamples = (value: unknown): Record<string, string[]> => {
  const source = asRecord(value)
  return {
    positive: asStringArray(source.positive),
    negative: asStringArray(source.negative),
  }
}

const firstDefined = <T,>(...values: Array<T | undefined>): T | undefined => (
  values.find((value) => value !== undefined)
)

const normalizeChatSkill = (value: unknown): ChatSkill => {
  const raw = asRecord(value)
  const installation = asRecord(raw.installation)
  const policy = asRecord(raw.policy)
  const packageData = asRecord(raw.package)
  const id = String(firstDefined(raw.id, raw.skill_id, raw.alias, packageData.id) ?? '')
  const tools = firstDefined(raw.tool_ids, raw.tools, installation.tool_ids, installation.tools)
  return {
    ...raw,
    id,
    name: String(firstDefined(raw.name, packageData.name, raw.alias, id) ?? id),
    label: String(firstDefined(raw.label, raw.name, packageData.label, packageData.name) ?? id),
    description: String(firstDefined(raw.description, packageData.description) ?? ''),
    tool_ids: asStringArray(tools),
    is_default: Boolean(firstDefined(raw.is_default, raw.default, installation.default, installation.default_selected) ?? false),
    enabled: Boolean(firstDefined(raw.enabled, installation.enabled) ?? true),
    status: String(firstDefined(raw.status, installation.status) ?? ''),
    origin: firstDefined(raw.origin, raw.provenance, packageData.origin) as string | SkillOrigin | undefined,
    version: firstDefined(raw.version, raw.active_version, packageData.version) as string | number | undefined,
    compatibility: firstDefined(raw.compatibility, raw.compatibility_report, packageData.compatibility) as string | SkillCompatibility | undefined,
    visibility: String(firstDefined(raw.visibility, installation.visibility) ?? 'public'),
    order: Number(firstDefined(raw.order, installation.order) ?? 100),
    always_on: Boolean(firstDefined(raw.always_on, policy.always_on) ?? false),
    routable: Boolean(firstDefined(raw.routable, policy.routable) ?? true),
    routing_examples: asRoutingExamples(firstDefined(raw.routing_examples, policy.routing_examples)),
    allowed_actions: Array.isArray(raw.allowed_actions) ? asStringArray(raw.allowed_actions) : undefined,
  }
}

const normalizeSkillDetail = (value: unknown): SkillDetail => {
  const raw = asRecord(value)
  const skill = asRecord(raw.skill)
  const packageData = asRecord(firstDefined(raw.package, raw.content))
  const installation = asRecord(firstDefined(raw.installation, raw.settings))
  const policy = asRecord(raw.policy)
  const merged = { ...skill, ...raw }
  const id = String(firstDefined(merged.id, merged.skill_id, merged.alias, packageData.id) ?? '')
  const tools = firstDefined(merged.tools, merged.tool_ids, installation.tools, installation.tool_ids)
  const rawResources = firstDefined(merged.resources, packageData.resources)
  const resources = Array.isArray(rawResources)
    ? rawResources.map((resource) => {
      const item = asRecord(resource)
      return {
        ...item,
        path: String(item.path ?? ''),
        kind: String(item.kind ?? item.type ?? ''),
        size: Number(item.size ?? 0),
        sha256: String(item.sha256 ?? item.digest ?? ''),
        executable: Boolean(item.executable ?? false),
      }
    }).filter((resource) => resource.path)
    : []
  return {
    ...raw,
    id,
    name: String(firstDefined(merged.name, packageData.name, merged.alias, id) ?? id),
    label: String(firstDefined(merged.label, merged.name, packageData.label, packageData.name) ?? id),
    description: String(firstDefined(merged.description, packageData.description) ?? ''),
    tools: asStringArray(tools),
    default: Boolean(firstDefined(merged.default, merged.is_default, installation.default, installation.default_selected) ?? false),
    enabled: Boolean(firstDefined(merged.enabled, installation.enabled) ?? true),
    visibility: String(firstDefined(merged.visibility, installation.visibility) ?? 'public'),
    order: Number(firstDefined(merged.order, installation.order) ?? 100),
    instructions: String(firstDefined(
      merged.instructions,
      merged.markdown,
      merged.skill_md,
      packageData.instructions,
      packageData.markdown,
      packageData.skill_md,
    ) ?? ''),
    frontmatter: asRecord(firstDefined(merged.frontmatter, packageData.frontmatter)),
    resources,
    always_on: Boolean(firstDefined(merged.always_on, policy.always_on) ?? false),
    routable: Boolean(firstDefined(merged.routable, policy.routable) ?? true),
    routing_examples: asRoutingExamples(firstDefined(merged.routing_examples, policy.routing_examples)),
    status: String(firstDefined(merged.status, installation.status) ?? ''),
    origin: firstDefined(merged.origin, merged.provenance, packageData.origin) as string | SkillOrigin | undefined,
    version: firstDefined(merged.version, merged.active_version, packageData.version) as string | number | undefined,
    version_id: String(firstDefined(merged.version_id, merged.active_version_id, packageData.version_id) ?? ''),
    revision: firstDefined(merged.revision, installation.revision, packageData.revision) as string | number | undefined,
    digest: String(firstDefined(merged.digest, packageData.digest) ?? ''),
    compatibility: firstDefined(merged.compatibility, merged.compatibility_report, packageData.compatibility) as string | SkillCompatibility | undefined,
    allowed_actions: Array.isArray(merged.allowed_actions) ? asStringArray(merged.allowed_actions) : undefined,
    license: String(firstDefined(merged.license, packageData.license) ?? ''),
  }
}

const assertSkillCatalog = (catalog: unknown): ChatSkillCatalog => {
  if (
    !catalog ||
    typeof catalog !== 'object' ||
    !Array.isArray((catalog as ChatSkillCatalog).skills) ||
    !Array.isArray((catalog as ChatSkillCatalog).tools)
  ) {
    throw new Error('Skill 列表暂时不可用')
  }
  const raw = catalog as ChatSkillCatalog
  return {
    ...raw,
    skills: raw.skills.map(normalizeChatSkill),
    tools: raw.tools,
    default_skill_ids: asStringArray(raw.default_skill_ids),
    default_tool_ids: asStringArray(raw.default_tool_ids),
    allowed_actions: Array.isArray(raw.allowed_actions) ? asStringArray(raw.allowed_actions) : undefined,
  }
}

const assertToolCatalog = (catalog: unknown): ToolCatalog => {
  if (
    !catalog ||
    typeof catalog !== 'object' ||
    !Array.isArray((catalog as ToolCatalog).tools)
  ) {
    throw new Error('工具列表暂时不可用')
  }
  return catalog as ToolCatalog
}

export const chatApi = {
  promptModes: async () => {
    const res = await client.get<ApiResponse<ChatPromptMode[]>>(endpoints.chatPromptModes)
    return res.data
  },
  skills: async () => {
    const res = await client.get<ApiResponse<ChatSkillCatalog>>(endpoints.chatSkills)
    return { ...res.data, data: assertSkillCatalog(res.data.data) }
  },
  skillCatalog: async () => {
    const res = await client.get<ApiResponse<ChatSkillCatalog>>(endpoints.skillCatalog)
    return { ...res.data, data: assertSkillCatalog(res.data.data) }
  },
  skillDetail: async (id: string) => {
    const res = await client.get<ApiResponse<unknown>>(endpoints.skillDetail(id))
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  createSkillDraft: async (payload: SkillDraftCreatePayload) => {
    const res = await client.post<ApiResponse<unknown>>(endpoints.skillDraftCreate, payload)
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  updateSkillDraft: async (id: string, payload: SkillDraftUpdatePayload) => {
    const res = await client.put<ApiResponse<unknown>>(endpoints.skillDraftUpdate(id), payload)
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  publishSkill: async (id: string, payload: SkillPublishPayload) => {
    const res = await client.post<ApiResponse<unknown>>(endpoints.skillPublish(id), payload)
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  importSkill: async (file: File) => {
    const body = new FormData()
    body.append('file', file)
    const res = await client.post<ApiResponse<SkillImportResult>>(
      endpoints.skillImports,
      body,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return res.data
  },
  skillImportDetail: async (id: string) => {
    const res = await client.get<ApiResponse<SkillImportResult>>(endpoints.skillImportDetail(id))
    return res.data
  },
  approveSkillImport: async (
    id: string,
    payload: SkillPublishPayload & { expected_digest: string },
  ) => {
    const res = await client.post<ApiResponse<unknown>>(endpoints.skillImportApprove(id), payload)
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  updateSkillSettings: async (id: string, payload: SkillSettingsPayload) => {
    const res = await client.patch<ApiResponse<unknown>>(endpoints.skillSettings(id), payload)
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  skillVersions: async (id: string) => {
    const res = await client.get<ApiResponse<SkillVersionsResponse | SkillVersion[]>>(endpoints.skillVersions(id))
    const data = res.data.data
    return {
      ...res.data,
      data: Array.isArray(data) ? { versions: data } : { ...data, versions: data?.versions || [] },
    }
  },
  activateSkillVersion: async (id: string, versionId: string, expectedRevision: number) => {
    const res = await client.post<ApiResponse<unknown>>(
      endpoints.skillVersionActivate(id, versionId),
      { expected_revision: expectedRevision },
    )
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  rollbackSkill: async (id: string, versionId: string, expectedRevision: number) => {
    const res = await client.post<ApiResponse<unknown>>(
      endpoints.skillRollback(id),
      { version_id: versionId, expected_revision: expectedRevision },
    )
    return { ...res.data, data: normalizeSkillDetail(res.data.data) }
  },
  exportSkill: async (id: string, versionId: string) => {
    const res = await client.get<Blob>(endpoints.skillVersionExport(id, versionId), { responseType: 'blob' })
    const disposition = String(res.headers['content-disposition'] || '')
    const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const plainName = disposition.match(/filename="?([^";]+)"?/i)?.[1]
    const filename = encodedName
      ? decodeURIComponent(encodedName)
      : plainName || `${id}.zip`
    return { blob: res.data, filename }
  },
  deleteSkill: async (id: string, expectedRevision: number) => {
    const res = await client.delete<ApiResponse>(endpoints.skillDelete(id), {
      data: { expected_revision: expectedRevision },
    })
    return res.data
  },
  toolCatalog: async () => {
    const res = await client.get<ApiResponse<ToolCatalog>>(endpoints.toolCatalog)
    return { ...res.data, data: assertToolCatalog(res.data.data) }
  },
  mcpPermissions: async () => {
    const res = await client.get<ApiResponse<McpPermissions>>(endpoints.mcpPermissions)
    return res.data
  },
  mcpServers: async () => {
    const res = await client.get<ApiResponse<McpServerCatalog>>(endpoints.mcpServers)
    return res.data
  },
  updateMcpTool: async (id: string, payload: Partial<Pick<
    ToolDetail,
    | 'label'
    | 'description'
    | 'enabled'
    | 'risk_level'
    | 'requires_confirmation'
    | 'timeout_seconds'
    | 'max_output_chars'
  >>) => {
    const res = await client.patch<ApiResponse<{ tool?: ToolDetail }>>(endpoints.mcpToolUpdate(id), payload)
    return res.data
  },
  updateMcpServer: async (id: string, payload: McpServerUpdatePayload) => {
    const res = await client.patch<ApiResponse>(endpoints.mcpServerUpdate(id), payload)
    return res.data
  },
  deleteMcpTool: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.mcpToolDelete(id))
    return res.data
  },
  deleteMcpServer: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.mcpServerDelete(id))
    return res.data
  },
  createTool: async (payload: ToolDetail) => {
    const res = await client.post<ApiResponse<ToolDetail>>(endpoints.toolCreate, payload)
    return res.data
  },
  updateTool: async (id: string, payload: ToolDetail) => {
    const res = await client.put<ApiResponse<ToolDetail>>(endpoints.toolUpdate(id), payload)
    return res.data
  },
  deleteTool: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.toolDelete(id))
    return res.data
  },
}
