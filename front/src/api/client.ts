import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { endpoints } from './endpoints'
import {
  clearAuthState,
  getAccessToken,
  getRefreshToken,
  useUserStore,
} from '../stores/useUserStore'

interface RefreshResponse {
  token: string
  refresh_token?: string
}

type RetryableRequest = InternalAxiosRequestConfig & { _authRetry?: boolean }

const client = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshRequest: Promise<string> | null = null

const refreshAccessToken = async () => {
  const refreshToken = getRefreshToken()
  if (!refreshToken) throw new Error('No refresh token')

  if (!refreshRequest) {
    refreshRequest = axios
      .post<RefreshResponse>(endpoints.refreshToken, { refresh_token: refreshToken })
      .then(({ data }) => {
        if (!data.token) throw new Error('Refresh response missing access token')
        useUserStore.getState().setTokens(data.token, data.refresh_token)
        return data.token
      })
      .finally(() => {
        refreshRequest = null
      })
  }
  return refreshRequest
}

const clearAuthAndRedirect = () => {
  clearAuthState()
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryableRequest | undefined
    const canRefresh = Boolean(
      getRefreshToken()
        && request
        && !request._authRetry
        && !request.url?.includes(endpoints.refreshToken)
    )

    if (error.response?.status === 401 && canRefresh && request) {
      request._authRetry = true
      try {
        const token = await refreshAccessToken()
        request.headers.Authorization = `Bearer ${token}`
        return client(request)
      } catch {
        clearAuthAndRedirect()
      }
    } else if (error.response?.status === 401) {
      clearAuthAndRedirect()
    }
    return Promise.reject(error)
  }
)

export default client
