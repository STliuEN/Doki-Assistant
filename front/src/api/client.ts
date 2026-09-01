import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { endpoints } from './endpoints'
import {
  clearAuthState,
  getAccessToken,
  useUserStore,
} from '../stores/useUserStore'

interface RefreshResponse {
  data: { token: string }
}

type RetryableRequest = InternalAxiosRequestConfig & { _authRetry?: boolean }

const client = axios.create({
  baseURL: '',
  timeout: 30000,
  withCredentials: true,
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
  if (!refreshRequest) {
    refreshRequest = axios
      .post<RefreshResponse>(endpoints.refreshToken, undefined, { withCredentials: true })
      .then(({ data }) => {
        if (!data.data?.token) throw new Error('Refresh response missing access token')
        useUserStore.getState().setToken(data.data.token)
        return data.data.token
      })
      .finally(() => {
        refreshRequest = null
      })
  }
  return refreshRequest
}

const isPublicAuthEndpoint = (url?: string) =>
  Boolean(url && (url.includes(endpoints.login) || url.includes(endpoints.register)))

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
        request
        && !request._authRetry
        && !request.url?.includes(endpoints.refreshToken)
        && !isPublicAuthEndpoint(request.url)
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
