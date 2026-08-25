import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  skillCatalog: vi.fn(),
  skills: vi.fn(),
  skillDetail: vi.fn(),
  skillVersions: vi.fn(),
  createSkillDraft: vi.fn(),
  updateSkillDraft: vi.fn(),
  publishSkill: vi.fn(),
  updateSkillSettings: vi.fn(),
  importSkill: vi.fn(),
  skillImportDetail: vi.fn(),
  approveSkillImport: vi.fn(),
  deleteSkill: vi.fn(),
  rollbackSkill: vi.fn(),
  exportSkill: vi.fn(),
}))

vi.mock('../api/chat', () => ({ chatApi: api }))

import SkillManager from './SkillManager'

const detail = {
  id: 'skill-1',
  name: 'research-helper',
  label: '资料助手',
  description: '处理资料',
  tools: [],
  default: false,
  enabled: false,
  visibility: 'public',
  order: 100,
  instructions: '# Existing instructions',
  frontmatter: {},
  resources: [{
    path: 'references/guide.md',
    kind: 'reference',
    size: 8,
    sha256: 'old-digest',
    executable: false,
  }],
  always_on: false,
  routable: true,
  routing_examples: { positive: [], negative: [] },
  revision: 1,
  version: 1,
  allowed_actions: ['update_draft', 'publish', 'update_settings'],
}

const catalog = {
  skills: [{
    id: detail.id,
    label: detail.label,
    description: detail.description,
    tool_ids: [],
    is_default: false,
    enabled: false,
    allowed_actions: detail.allowed_actions,
  }],
  tools: [],
  default_skill_ids: [],
  default_tool_ids: [],
  allowed_actions: ['create_draft', 'import_package'],
}

const responseDetail = (overrides: Record<string, unknown> = {}) => ({
  data: { ...detail, ...overrides },
})

const resourceFile = (name: string, bytes: number[]) => {
  const file = new File([Uint8Array.from(bytes)], name, { type: 'application/octet-stream' })
  Object.defineProperty(file, 'arrayBuffer', {
    value: async () => Uint8Array.from(bytes).buffer,
  })
  return file
}

const renderManager = async () => {
  render(<SkillManager />)
  await screen.findByText('references/guide.md')
}

const saveAndWaitForDraft = async () => {
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(api.updateSkillDraft).toHaveBeenCalledTimes(1))
}

describe('SkillManager resource editing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.skillCatalog.mockResolvedValue({ data: catalog })
    api.skills.mockResolvedValue({ data: catalog })
    api.skillDetail.mockResolvedValue(responseDetail())
    api.skillVersions.mockResolvedValue({ data: { versions: [] } })
    api.createSkillDraft.mockResolvedValue(responseDetail({ id: 'created-skill', revision: 2 }))
    api.updateSkillDraft.mockResolvedValue(responseDetail({ revision: 2 }))
    api.publishSkill.mockResolvedValue(responseDetail({ revision: 3 }))
    api.updateSkillSettings.mockResolvedValue(responseDetail({ revision: 2 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('does not send resource_changes when existing resources are untouched', async () => {
    await renderManager()
    fireEvent.change(screen.getByDisplayValue('# Existing instructions'), {
      target: { value: '# Updated instructions' },
    })

    await saveAndWaitForDraft()

    expect(api.updateSkillDraft.mock.calls[0][1]).not.toHaveProperty('resource_changes')
  })

  it('sends only the replacement resource in resource_changes.upsert', async () => {
    await renderManager()
    fireEvent.click(screen.getByTitle('替换 references/guide.md'))
    fireEvent.change(screen.getByLabelText('选择 Skill 资源文件'), {
      target: { files: [resourceFile('guide.md', [0, 255, 1])] },
    })
    await screen.findByText('待替换')

    await saveAndWaitForDraft()

    expect(api.updateSkillDraft.mock.calls[0][1]).toMatchObject({
      resource_changes: {
        upsert: [{ path: 'references/guide.md', content_base64: 'AP8B' }],
        delete: [],
      },
    })
    expect(api.updateSkillDraft.mock.calls[0][1]).not.toHaveProperty('resources')
  })

  it('sends an existing resource deletion without resending other resources', async () => {
    await renderManager()
    fireEvent.click(screen.getByTitle('删除 references/guide.md'))
    await screen.findByText('references/guide.md · 待删除')

    await saveAndWaitForDraft()

    expect(api.updateSkillDraft.mock.calls[0][1]).toMatchObject({
      resource_changes: {
        upsert: [],
        delete: ['references/guide.md'],
      },
    })
    expect(api.updateSkillDraft.mock.calls[0][1]).not.toHaveProperty('resources')
  })

  it('sends the complete resource list when creating a Skill', async () => {
    await renderManager()
    fireEvent.click(screen.getByTitle('新增 Skill'))
    fireEvent.change(screen.getByLabelText('资源路径'), {
      target: { value: 'assets/icon.bin' },
    })
    fireEvent.click(screen.getByRole('button', { name: '上传' }))
    fireEvent.change(screen.getByLabelText('选择 Skill 资源文件'), {
      target: { files: [resourceFile('icon.bin', [1, 2, 3])] },
    })
    await screen.findByText('待新增')

    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.createSkillDraft).toHaveBeenCalledTimes(1))

    expect(api.createSkillDraft.mock.calls[0][0]).toMatchObject({
      resources: [{ path: 'assets/icon.bin', content_base64: 'AQID' }],
    })
    expect(api.createSkillDraft.mock.calls[0][0]).not.toHaveProperty('resource_changes')
  })

  it('allows a format-compatible executable package to install disabled', async () => {
    api.importSkill.mockResolvedValue({
      data: {
        id: 'import-c',
        status: 'awaiting_approval',
        digest: 'c'.repeat(64),
        name: 'scripted-skill',
        compatibility: {
          level: 'C',
          format_compatible: true,
          runtime_ready: false,
          reasons: ['Executable packages require the isolated runner.'],
        },
      },
    })
    api.approveSkillImport.mockResolvedValue(responseDetail({ id: 'scripted-skill' }))
    await renderManager()

    const importInput = document.querySelector<HTMLInputElement>('input[accept=".zip,application/zip"]')
    expect(importInput).not.toBeNull()
    fireEvent.change(importInput!, {
      target: { files: [new File(['zip'], 'scripted-skill.zip', { type: 'application/zip' })] },
    })

    const approveButton = await screen.findByRole('button', { name: '批准并安装' })
    expect((approveButton as HTMLButtonElement).disabled).toBe(false)
    expect(await screen.findByText('可安装和管理，但在隔离运行时就绪前会保持禁用。')).toBeTruthy()
    fireEvent.click(approveButton)

    await waitFor(() => expect(api.approveSkillImport).toHaveBeenCalledTimes(1))
    expect(api.approveSkillImport.mock.calls[0][1]).toMatchObject({
      expected_digest: 'c'.repeat(64),
      expected_revision: 0,
      enabled: false,
      default: false,
    })
  })

  it('archives with the revision currently shown in the editor', async () => {
    api.skillDetail.mockResolvedValue(responseDetail({
      allowed_actions: [...detail.allowed_actions, 'archive'],
    }))
    api.deleteSkill.mockResolvedValue({ code: 200, message: 'ok' })
    await renderManager()

    fireEvent.click(screen.getByRole('button', { name: '归档' }))

    await waitFor(() => expect(api.deleteSkill).toHaveBeenCalledWith('skill-1', 1))
  })
})
