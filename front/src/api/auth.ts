import client from './client'
import { endpoints } from './endpoints'
import type { UserInfo } from '../types/api'

interface LoginResponseData {
  user: UserInfo
  token: string
  expire_time: number
}

interface ApiEnvelope<T> {
  code: number | string
  message: string
  data: T
  correlation_id?: string
}

interface RegisterResponseData {
  user: UserInfo
  token: string
  expire_time: number
}

interface ActionResponseData {
  user?: UserInfo
  token?: string
  expire_time?: number
}

export const authErrorMessage = (error: unknown, fallback: string) => {
  const message = (error as { response?: { data?: { message?: unknown } } })?.response?.data?.message
  return typeof message === 'string' && message ? message : fallback
}

export const authApi = {
  login: async (username: string, password: string) => {
    const res = await client.post<ApiEnvelope<LoginResponseData>>(endpoints.login, { username, password })
    return res.data.data
  },

  register: async (data: { username: string; password: string; email: string; telephone?: string; confirm_password: string }) => {
    const res = await client.post<ApiEnvelope<RegisterResponseData>>(endpoints.register, data)
    return res.data.data
  },

  logout: async () => {
    const res = await client.post<ApiEnvelope<ActionResponseData | null>>(endpoints.logout)
    return res.data.data
  },

  getProfile: async () => {
    const res = await client.get<ApiEnvelope<UserInfo>>(endpoints.profile)
    return res.data.data
  },

  updateProfile: async (data: Record<string, unknown>) => {
    const res = await client.put<ApiEnvelope<ActionResponseData>>(endpoints.userUpdate, data)
    return res.data.data
  },

  updatePassword: async (oldPassword: string, newPassword: string) => {
    const res = await client.post<ApiEnvelope<ActionResponseData>>(endpoints.changePassword, {
      old_password: oldPassword,
      new_password: newPassword,
      confirm_password: newPassword,
    })
    return res.data.data
  },
}
