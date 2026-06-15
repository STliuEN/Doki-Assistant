import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse, ModelConfig, ModelConfigPayload, OllamaModelsResponse } from '../types/api'

export const modelConfigApi = {
  list: async () => {
    const res = await client.get<ApiResponse<ModelConfig[]>>(endpoints.modelConfigList)
    return res.data
  },

  systemDefault: async () => {
    const res = await client.get<ApiResponse<ModelConfig>>(endpoints.modelConfigSystemDefault)
    return res.data
  },

  create: async (payload: ModelConfigPayload) => {
    const res = await client.post<ApiResponse<ModelConfig>>(endpoints.modelConfigCreate, payload)
    return res.data
  },

  update: async (id: string, payload: Partial<ModelConfigPayload>) => {
    const res = await client.put<ApiResponse<ModelConfig>>(endpoints.modelConfigUpdate(id), payload)
    return res.data
  },

  delete: async (id: string) => {
    const res = await client.delete<ApiResponse>(endpoints.modelConfigDelete(id))
    return res.data
  },

  setDefault: async (id: string) => {
    const res = await client.post<ApiResponse<ModelConfig>>(endpoints.modelConfigSetDefault(id))
    return res.data
  },

  test: async (payload: ModelConfigPayload) => {
    const res = await client.post<ApiResponse<{ ok: boolean; result: string; error: string }>>(endpoints.modelConfigTest, payload)
    return res.data
  },

  testSaved: async (id: string) => {
    const res = await client.post<ApiResponse<{ ok: boolean; result: string; error: string }>>(endpoints.modelConfigTestSaved(id))
    return res.data
  },

  testSystemDefault: async () => {
    const res = await client.post<ApiResponse<{ ok: boolean; result: string; error: string }>>(endpoints.modelConfigTestSystemDefault)
    return res.data
  },

  listOllamaModels: async (baseUrl: string) => {
    const res = await client.get<ApiResponse<OllamaModelsResponse>>(endpoints.modelConfigOllamaModels, {
      params: { base_url: baseUrl },
    })
    return res.data
  },
}
