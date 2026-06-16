import client from './client'
import { endpoints } from './endpoints'
import type { ApiResponse, EmbeddingConfig, EmbeddingSwitchResult, KnowledgeDocument, KnowledgeDocumentDetail, OllamaModelsResponse } from '../types/api'

interface KnowledgeListData {
  documents: KnowledgeDocument[]
  total_count: number
}

export const knowledgeApi = {
  list: async () => {
    const res = await client.get<ApiResponse<KnowledgeListData>>(endpoints.knowledgeList)
    return res.data
  },

  detail: async (filename: string) => {
    const res = await client.get<ApiResponse<KnowledgeDocumentDetail>>(endpoints.knowledgeDetail, { params: { filename } })
    return res.data
  },

  chunks: async (filename: string) => {
    const res = await client.get<ApiResponse<unknown[]>>(endpoints.knowledgeChunks, { params: { filename } })
    return res.data
  },

  sourceUrl: (filename: string) => `${endpoints.knowledgeSource}?filename=${encodeURIComponent(filename)}`,

  deleteByFilename: async (filename: string) => {
    const res = await client.delete<ApiResponse<null>>(endpoints.knowledgeDeleteFilename, { params: { filename } })
    return res.data
  },

  deleteByMd5: async (md5: string) => {
    const res = await client.delete<ApiResponse<null>>(endpoints.knowledgeMd5Delete(md5))
    return res.data
  },

  cleanAll: async () => {
    const res = await client.delete<ApiResponse<null>>(endpoints.cleanVectors)
    return res.data
  },

  currentEmbedding: async () => {
    const res = await client.get<ApiResponse<EmbeddingConfig>>(endpoints.knowledgeEmbeddingCurrent)
    return res.data
  },

  listEmbeddingOllamaModels: async (baseUrl: string) => {
    const res = await client.get<ApiResponse<OllamaModelsResponse>>(endpoints.knowledgeEmbeddingOllamaModels, {
      params: { base_url: baseUrl },
    })
    return res.data
  },

  switchEmbedding: async (payload: { model_name: string; base_url?: string; provider?: string; model_type?: string }) => {
    const res = await client.post<ApiResponse<EmbeddingSwitchResult>>(endpoints.knowledgeEmbeddingSwitch, payload)
    return res.data
  },
}
