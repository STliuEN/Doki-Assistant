import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse, ChatHistoryMessage, ChatSession } from '../types/api'

interface SessionsData {
  sessions: ChatSession[]
}

interface SessionDetailData {
  session_id: string
  history: [string, string][]
}

interface SessionMessagesData {
  session_id: string
  messages: ChatHistoryMessage[]
}

interface DeleteMessageData {
  session_id: string
  deleted_ids: number[]
}

export const sessionsApi = {
  list: async (userId: string) => {
    const res = await client.get<ApiResponse<SessionsData>>(endpoints.getUserSessions(userId))
    return res.data
  },

  get: async (id: string) => {
    const res = await client.get<ApiResponse<SessionDetailData>>(endpoints.getSession(id))
    return res.data
  },

  messages: async (id: string) => {
    const res = await client.get<ApiResponse<SessionMessagesData>>(endpoints.getSessionMessages(id))
    return res.data
  },

  deleteMessage: async (sessionId: string, messageId: number, mode = 'single') => {
    const res = await client.delete<ApiResponse<DeleteMessageData>>(endpoints.deleteSessionMessage(sessionId, messageId, mode))
    return res.data
  },

  delete: async (id: string) => {
    const res = await client.delete<ApiResponse<null>>(endpoints.deleteSession(id))
    return res.data
  },
}
