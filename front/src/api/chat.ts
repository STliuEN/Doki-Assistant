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
}

export interface ChatSkillCatalog {
  skills: ChatSkill[]
  tools: ChatTool[]
  default_skill_ids: string[]
  default_tool_ids: string[]
}

export interface SkillDetail {
  id: string
  label: string
  description: string
  tools: string[]
  default: boolean
  visibility: string
  order: number
  instructions: string
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

const assertSkillCatalog = (catalog: unknown): ChatSkillCatalog => {
  if (
    !catalog ||
    typeof catalog !== 'object' ||
    !Array.isArray((catalog as ChatSkillCatalog).skills) ||
    !Array.isArray((catalog as ChatSkillCatalog).tools)
  ) {
    throw new Error('Skill 列表暂时不可用')
  }
  return catalog as ChatSkillCatalog
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
    const res = await client.get<ApiResponse<SkillDetail>>(endpoints.skillDetail(id))
    return res.data
  },
  createSkill: async (payload: SkillDetail) => {
    const res = await client.post<ApiResponse<SkillDetail>>(endpoints.skillCreate, payload)
    return res.data
  },
  updateSkill: async (id: string, payload: SkillDetail) => {
    const res = await client.put<ApiResponse<SkillDetail>>(endpoints.skillUpdate(id), payload)
    return res.data
  },
  deleteSkill: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.skillDelete(id))
    return res.data
  },
  toolCatalog: async () => {
    const res = await client.get<ApiResponse<ToolCatalog>>(endpoints.toolCatalog)
    return { ...res.data, data: assertToolCatalog(res.data.data) }
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
