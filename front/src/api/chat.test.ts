import type { AxiosAdapter, AxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it } from 'vitest'

import client from './client'
import { chatApi } from './chat'

const originalAdapter = client.defaults.adapter

const response = (config: AxiosRequestConfig, data: unknown, headers: Record<string, string> = {}) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers,
  config,
})

const requestBody = (config: AxiosRequestConfig) => (
  typeof config.data === 'string' ? JSON.parse(config.data) : config.data
)

afterEach(() => {
  client.defaults.adapter = originalAdapter
})

describe('standard Skill API contract', () => {
  it('normalizes additive domain fields without breaking the chat catalog shape', async () => {
    client.defaults.adapter = (async (config) => {
      if (config.url === '/api/skills/catalog') {
        return response(config, {
          code: 200,
          message: 'ok',
          data: {
            revision: 9,
            allowed_actions: ['create_draft', 'import_package'],
            skills: [{
              id: 'skill-uuid',
              name: 'research-helper',
              label: '资料助手',
              description: '处理资料',
              installation: {
                enabled: false,
                default_selected: true,
                visibility: 'private',
                order: 12,
                tools: ['mcp_search'],
              },
              policy: {
                always_on: false,
                routable: true,
                routing_examples: { positive: ['查资料'] },
              },
              package: {
                version: 3,
                origin: { type: 'import', author: 'Example' },
                compatibility: { level: 'B Resources', runtime_ready: true },
              },
              future_field: { preserved: true },
            }],
            tools: [],
            default_skill_ids: ['skill-uuid'],
            default_tool_ids: [],
          },
        })
      }

      return response(config, {
        code: 200,
        message: 'ok',
        data: {
          skill: { id: 'skill-uuid', name: 'research-helper' },
          package: {
            label: '资料助手',
            description: '处理资料',
            instructions: '# Instructions',
            version: 3,
            version_id: 'version-3',
            digest: 'abc123',
            frontmatter: { license: 'MIT' },
            resources: [{ path: 'references/guide.md', size: 12 }],
          },
          installation: { enabled: false, default_selected: true, tools: ['mcp_search'] },
          policy: { routable: true, routing_examples: { positive: ['查资料'] } },
          allowed_actions: ['update_draft', 'publish'],
        },
      })
    }) as AxiosAdapter

    const catalog = (await chatApi.skillCatalog()).data
    expect(catalog.skills[0]).toMatchObject({
      id: 'skill-uuid',
      label: '资料助手',
      tool_ids: ['mcp_search'],
      is_default: true,
      enabled: false,
      visibility: 'private',
      version: 3,
      future_field: { preserved: true },
    })

    const detail = (await chatApi.skillDetail('skill-uuid')).data
    expect(detail).toMatchObject({
      id: 'skill-uuid',
      name: 'research-helper',
      instructions: '# Instructions',
      version_id: 'version-3',
      tools: ['mcp_search'],
      enabled: false,
      default: true,
      allowed_actions: ['update_draft', 'publish'],
      resources: [{ path: 'references/guide.md', size: 12 }],
    })
  })

  it('uses the versioned draft, publish, settings, import and rollback endpoints', async () => {
    const requests: AxiosRequestConfig[] = []
    client.defaults.adapter = (async (config) => {
      requests.push(config)
      if (config.url === '/api/skills/imports/import-1') {
        return response(config, {
          code: 200,
          message: 'ok',
          data: { id: 'import-1', status: 'awaiting_approval', digest: 'a'.repeat(64) },
        })
      }
      return response(config, {
        code: 200,
        message: 'ok',
        data: {
          id: 'skill-uuid',
          name: 'new-skill',
          label: 'New Skill',
          description: 'Description',
          revision: 2,
        },
      })
    }) as AxiosAdapter

    const draft = {
      name: 'new-skill',
      display_name: 'New Skill',
      description: 'Description',
      instructions: '# New Skill',
    }
    const settings = {
      expected_revision: 2,
      enabled: false,
      default: false,
      visibility: 'public',
      order: 100,
      tools: [],
      always_on: false,
      routable: true,
      routing_examples: { positive: [], negative: [] },
    }

    await chatApi.createSkillDraft(draft)
    await chatApi.updateSkillDraft('skill-uuid', { ...draft, expected_revision: 1 })
    await chatApi.publishSkill('skill-uuid', settings)
    await chatApi.updateSkillSettings('skill-uuid', settings)
    await chatApi.skillImportDetail('import-1')
    await chatApi.approveSkillImport('import-1', { ...settings, expected_digest: 'a'.repeat(64) })
    await chatApi.rollbackSkill('skill-uuid', 'version-1', 2)
    await chatApi.deleteSkill('skill-uuid', 2)

    expect(requests.map(({ method, url }) => [method, url])).toEqual([
      ['post', '/api/skills/drafts'],
      ['put', '/api/skills/skill-uuid/draft'],
      ['post', '/api/skills/skill-uuid/publish'],
      ['patch', '/api/skills/skill-uuid/settings'],
      ['get', '/api/skills/imports/import-1'],
      ['post', '/api/skills/imports/import-1/approve'],
      ['post', '/api/skills/skill-uuid/rollback'],
      ['delete', '/api/skills/skill-uuid'],
    ])
    expect(requestBody(requests[2])).toMatchObject({ expected_revision: 2, enabled: false })
    expect(requestBody(requests[1])).not.toHaveProperty('resources')
    expect(requestBody(requests[5])).toMatchObject({ expected_digest: 'a'.repeat(64) })
    expect(requestBody(requests[6])).toEqual({ version_id: 'version-1', expected_revision: 2 })
    expect(requestBody(requests[7])).toEqual({ expected_revision: 2 })
  })
})
