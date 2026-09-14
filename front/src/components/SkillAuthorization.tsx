import { useCallback, useEffect, useState } from 'react'
import client from '../api/client'

interface Grant {
  id: string
  status: string
  policy_revision: number
  subject_revision: number
  content_digest: string
  expires_at: string | null
  grant: { package_digest: string; capabilities: { tools: string[]; resources: { read: string[] } } }
}
interface Review {
  revision: number
  authorization: Grant | null
  can_request: boolean
  can_decide: boolean
}

export default function SkillAuthorization({ identifier, revision, onChanged }: {
  identifier: string; revision?: number; onChanged: () => Promise<void>
}) {
  const [review, setReview] = useState<Review | null>(null)
  const [reason, setReason] = useState('')
  const [days, setDays] = useState(30)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const base = `/api/skills/${encodeURIComponent(identifier)}/authorization`
  const reload = useCallback(async () => {
    try {
      const response = await client.get<{ data: Review }>(base)
      setReview(response.data.data)
      setError('')
    } catch {
      setReview(null)
      setError('授权状态暂不可用，请先发布版本并刷新。')
    }
  }, [base])
  useEffect(() => {
    const timer = window.setTimeout(() => { void reload() }, 0)
    return () => window.clearTimeout(timer)
  }, [reload, revision])
  const grant = review?.authorization
  const act = async (decision: 'request' | 'approve' | 'revoke') => {
    if (!review || !reason.trim()) return
    setBusy(true)
    try {
      if (decision === 'request') {
        await client.post(base, { expected_revision: review.revision, reason,
          expires_at: new Date(Date.now() + days * 86400000).toISOString() })
      } else if (grant) {
        await client.post(`${base}/${grant.id}/${decision}`, { reason,
          expected_policy_revision: grant.policy_revision, expected_subject_revision: grant.subject_revision,
          expected_content_digest: grant.content_digest })
      }
      await reload()
      await onChanged()
    } catch (failure) {
      const message = (failure as { response?: { data?: { message?: string } } }).response?.data?.message
      setError(message || '操作未完成，请刷新授权状态后重试。')
    } finally { setBusy(false) }
  }
  const statuses: Record<string, string> = { requested: '等待独立安全管理员审批', approved: '已批准，可在管理设置启用', revoked: '已撤销' }
  return <section aria-label="Skill 安全授权" className="space-y-3 rounded-lg border border-[var(--color-border)] p-4 text-sm">
    <h3 className="font-semibold">安全授权</h3>
    <p>{grant ? statuses[grant.status] || grant.status : '尚无安全授权'}</p>
    <p className="text-[var(--color-text-secondary)]">保存或发布内容后，由 Skill 管理员提交申请，另一位安全管理员核对并批准，然后启用。更换版本或能力需要重新审批。</p>
    {grant && <div className="space-y-1">
      <p>工具：{grant.grant.capabilities.tools.join('、') || '无'}</p>
      <p>可读资源：{grant.grant.capabilities.resources.read.join('、') || '无'}</p>
      <p>到期时间：{grant.expires_at ? new Date(grant.expires_at).toLocaleString() : '未设置'}</p>
      <p className="break-all text-xs">已审内容摘要：{grant.grant.package_digest}</p>
    </div>}
    <label className="block">申请或决定理由
      <input aria-label="授权理由" value={reason} onChange={event => setReason(event.target.value)} maxLength={4096}
        className="mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2" />
    </label>
    {review?.can_request && <label className="block">有效天数
      <input aria-label="授权有效天数" type="number" min={1} max={365} value={days}
        onChange={event => setDays(Math.min(365, Math.max(1, Number(event.target.value) || 1)))} className="ml-3 w-20" />
    </label>}
    <div className="flex gap-3">
      {review?.can_request && <button type="button" disabled={busy || !reason.trim()} onClick={() => void act('request')}>提交授权申请</button>}
      {review?.can_decide && grant?.status === 'requested' &&
        <button type="button" disabled={busy || !reason.trim()} onClick={() => void act('approve')}>批准授权</button>}
      {review?.can_decide && grant?.status === 'approved' &&
        <button type="button" disabled={busy || !reason.trim()} onClick={() => void act('revoke')}>撤销授权</button>}
      <button type="button" disabled={busy} onClick={() => void reload()}>刷新状态</button>
    </div>
    {error && <p role="alert" className="text-[var(--color-danger)]">{error}</p>}
  </section>
}
