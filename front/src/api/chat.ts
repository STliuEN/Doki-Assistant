import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse } from '../types/api'

export interface ChatPromptMode {
  value: string
  label: string
}

export const chatApi = {
  promptModes: async () => {
    const res = await client.get<ApiResponse<ChatPromptMode[]>>(endpoints.chatPromptModes)
    return res.data
  },
}
