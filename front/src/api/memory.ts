import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse, MemoryItem, MemoryListData, MemoryPayload, MemoryQuestion } from '../types/api'

export const memoryApi = {
  today: async () => {
    const res = await client.get<ApiResponse<MemoryListData>>(endpoints.memoryToday)
    return res.data.data
  },

  list: async (params?: { type?: string; status?: string }) => {
    const res = await client.get<ApiResponse<MemoryListData>>(endpoints.memoryList, { params })
    return res.data.data
  },

  get: async (id: string) => {
    const res = await client.get<ApiResponse<MemoryItem>>(endpoints.memoryDetail(id))
    return res.data.data
  },

  create: async (payload: MemoryPayload) => {
    const res = await client.post<ApiResponse<MemoryItem>>(endpoints.memoryCreate, payload)
    return res.data.data
  },

  update: async (id: string, payload: Partial<MemoryPayload>) => {
    const res = await client.put<ApiResponse<MemoryItem>>(endpoints.memoryUpdate(id), payload)
    return res.data.data
  },

  complete: async (id: string) => {
    const res = await client.post<ApiResponse>(endpoints.memoryComplete(id))
    return res.data
  },

  reviewed: async (id: string) => {
    const res = await client.post<ApiResponse>(endpoints.memoryReviewed(id))
    return res.data
  },

  postpone: async (id: string, days: number) => {
    const res = await client.post<ApiResponse>(endpoints.memoryPostpone(id), { days })
    return res.data
  },

  archive: async (id: string) => {
    const res = await client.post<ApiResponse>(endpoints.memoryArchive(id))
    return res.data
  },

  delete: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.memoryDelete(id))
    return res.data
  },

  getReviewQuestion: async (id: string) => {
    const res = await client.get<ApiResponse<MemoryQuestion>>(endpoints.memoryReviewQuestion(id))
    return res.data.data
  },
}
