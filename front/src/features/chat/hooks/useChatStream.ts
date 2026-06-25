import { useCallback, useEffect, useRef } from 'react'
import { useSSE } from '../../../hooks/useSSE'
import { formatThinkingDetail } from '../storage'
import type { Message } from '../types'

type StreamHandlers = {
  /** 思考事件回调（已格式化 detail 由调用方处理 stage/steps）。 */
  onThinking?: (stage: string, content?: string, details?: Record<string, unknown>) => void
  /** 首个 response 增量到达（用于切换 thinking 折叠等一次性副作用）。 */
  onFirstResponse?: () => void
  /** response 事件携带的 session_id（query 流会用到）。 */
  onSessionId?: (sessionId: string) => void
  /** 流正常结束。 */
  onDone?: (sessionId?: string) => void
  /** 出错。 */
  onError?: (error: string) => void
}

type RunStreamArgs = {
  url: string
  body: Record<string, unknown>
  /** 重新生成时传入目标 assistant 消息 id，response 增量将覆盖该消息；不传则追加/更新末条 assistant。 */
  regenerateMessageId?: number | null
  handlers?: StreamHandlers
}

/**
 * 统一 Chat 流式消费：把 useSSE 的 token 增量按 rAF 批量 flush 进 messages，
 * 并封装「追加末条 assistant」与「覆盖指定 assistant」两种落点。
 * handleSend / handleConfirmAction / handleRegenerateMessage 共用本 hook，消除三处重复的 ref+rAF 机制。
 */
export function useChatStream(setMessages: React.Dispatch<React.SetStateAction<Message[]>>) {
  const { start, loading } = useSSE()
  const contentRef = useRef('')
  const regeneratingMessageIdRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  const flushContent = useCallback(() => {
    setMessages((prev) => {
      if (regeneratingMessageIdRef.current !== null) {
        return prev.map((message) => (
          message.id === regeneratingMessageIdRef.current
            ? { ...message, content: contentRef.current }
            : message
        ))
      }
      const newMsgs = [...prev]
      const last = newMsgs[newMsgs.length - 1]
      if (last?.role === 'assistant') {
        newMsgs[newMsgs.length - 1] = { ...last, content: contentRef.current }
      } else {
        newMsgs.push({ role: 'assistant', content: contentRef.current })
      }
      return newMsgs
    })
  }, [setMessages])

  const cancelRaf = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [])

  const scheduleFlush = useCallback(() => {
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null
        flushContent()
      })
    }
  }, [flushContent])

  useEffect(() => cancelRaf, [cancelRaf])

  const runStream = useCallback(async ({ url, body, regenerateMessageId = null, handlers = {} }: RunStreamArgs) => {
    contentRef.current = ''
    regeneratingMessageIdRef.current = regenerateMessageId
    let firstResponseSeen = false

    await start(url, body, {
      onThinking: handlers.onThinking,
      onResponse: (content, sessionId) => {
        if (!firstResponseSeen) {
          firstResponseSeen = true
          handlers.onFirstResponse?.()
        }
        if (sessionId) handlers.onSessionId?.(sessionId)
        contentRef.current += content
        scheduleFlush()
      },
      onDone: (sessionId) => {
        cancelRaf()
        flushContent()
        regeneratingMessageIdRef.current = null
        handlers.onDone?.(sessionId)
      },
      onError: (error) => {
        cancelRaf()
        regeneratingMessageIdRef.current = null
        handlers.onError?.(error)
      },
    })
  }, [start, scheduleFlush, cancelRaf, flushContent])

  return { runStream, loading, formatThinkingDetail }
}
