import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStream } from '../hooks/useChatStream'
import type { Message } from '../types'

type FetchResponse = {
  ok: boolean
  status: number
  body: ReadableStream<Uint8Array> | null
}

const encoder = new TextEncoder()

function sse(payload: Record<string, unknown>) {
  return `data: ${JSON.stringify(payload)}\n\n`
}

function streamFromChunks(chunks: string[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

function mockFetchChunks(chunks: string[]) {
  vi.stubGlobal('fetch', vi.fn(async (): Promise<FetchResponse> => ({
    ok: true,
    status: 200,
    body: streamFromChunks(chunks),
  })))
}

function renderChatHook(initialMessages: Message[] = []) {
  let messages = initialMessages
  const setMessages = vi.fn((updater: React.SetStateAction<Message[]>) => {
    messages = typeof updater === 'function'
      ? (updater as (previous: Message[]) => Message[])(messages)
      : updater
  })
  const hook = renderHook(() => useChatStream(setMessages))
  return { hook, setMessages, getMessages: () => messages }
}

describe('useChatStream', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('parses data lines split across chunks and passes done session id', async () => {
    const done = vi.fn()
    const sessionIds: string[] = []
    const frame = sse({ type: 'response', content: 'chunk', session_id: 'sess-1' })
    mockFetchChunks([
      frame.slice(0, 10),
      frame.slice(10),
      sse({ type: 'done', session_id: 'sess-1' }),
    ])
    const { hook, getMessages } = renderChatHook()

    await act(async () => {
      await hook.result.current.runStream({
        url: '/chat/agent/',
        body: {},
        handlers: {
          onSessionId: (sessionId) => sessionIds.push(sessionId),
          onDone: done,
        },
      })
    })

    expect(getMessages()).toEqual([{ role: 'assistant', content: 'chunk' }])
    expect(sessionIds).toEqual(['sess-1'])
    expect(done).toHaveBeenCalledWith('sess-1')
  })

  it('flushes buffered response before thinking events', async () => {
    const thinking = vi.fn()
    mockFetchChunks([
      sse({ type: 'response', content: 'before ', session_id: 'sess-2' }),
      sse({ type: 'thinking', stage: 'tool_start', content: 'tool' }),
      sse({ type: 'response', content: 'after', session_id: 'sess-2' }),
      sse({ type: 'done', session_id: 'sess-2' }),
    ])
    const { hook, getMessages } = renderChatHook()

    await act(async () => {
      await hook.result.current.runStream({
        url: '/chat/agent/',
        body: {},
        handlers: { onThinking: thinking },
      })
    })

    expect(thinking).toHaveBeenCalledWith('tool_start', 'tool', undefined)
    expect(getMessages()).toEqual([{ role: 'assistant', content: 'before after' }])
  })

  it('flushes buffered response before error events', async () => {
    const error = vi.fn()
    mockFetchChunks([
      sse({ type: 'response', content: 'partial', session_id: 'sess-3' }),
      sse({ type: 'error', content: 'boom', session_id: 'sess-3' }),
      sse({ type: 'done', session_id: 'sess-3' }),
    ])
    const { hook, getMessages } = renderChatHook()

    await act(async () => {
      await hook.result.current.runStream({
        url: '/chat/agent/',
        body: {},
        handlers: { onError: error },
      })
    })

    expect(error).toHaveBeenCalledWith('boom')
    expect(getMessages()).toEqual([{ role: 'assistant', content: 'partial' }])
  })

  it('regenerate updates the target assistant message instead of appending', async () => {
    mockFetchChunks([
      sse({ type: 'response', content: 'new answer', session_id: 'sess-4' }),
      sse({ type: 'done', session_id: 'sess-4' }),
    ])
    const { hook, getMessages } = renderChatHook([
      { id: 1, role: 'user', content: 'question' },
      { id: 2, role: 'assistant', content: 'old answer' },
    ])

    await act(async () => {
      await hook.result.current.runStream({
        url: '/chat/agent/regenerate',
        body: {},
        regenerateMessageId: 2,
      })
    })

    expect(getMessages()).toEqual([
      { id: 1, role: 'user', content: 'question' },
      { id: 2, role: 'assistant', content: 'new answer' },
    ])
  })
})
