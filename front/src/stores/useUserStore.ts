import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserInfo } from '../types/api'

interface UserState {
  userInfo: UserInfo | null
  token: string
  refreshToken: string
  isLogin: boolean
  userBio: string
  login: (token: string, user: UserInfo, refreshToken?: string) => void
  logout: () => void
  setUserInfo: (info: UserInfo) => void
  setToken: (token: string) => void
  setTokens: (token: string, refreshToken?: string) => void
  setUserBio: (bio: string) => void
}

const LEGACY_JWT_KEY = 'jwt_token'

const readLegacyToken = () => {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem(LEGACY_JWT_KEY) || ''
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      userInfo: null,
      token: readLegacyToken(),
      refreshToken: '',
      isLogin: Boolean(readLegacyToken()),
      userBio: '',
      login: (token, user, refreshToken = '') => {
        localStorage.removeItem(LEGACY_JWT_KEY)
        set({ token, refreshToken, userInfo: user, isLogin: true })
      },
      logout: () => {
        localStorage.removeItem(LEGACY_JWT_KEY)
        set({ token: '', refreshToken: '', userInfo: null, isLogin: false, userBio: '' })
      },
      setUserInfo: (info) => set({ userInfo: info }),
      setToken: (token) => set({ token }),
      setTokens: (token, refreshToken) => set((state) => ({
        token,
        refreshToken: refreshToken ?? state.refreshToken,
        isLogin: Boolean(token),
      })),
      setUserBio: (bio) => set({ userBio: bio }),
    }),
    { name: 'user-store' }
  )
)

export const getAccessToken = () => useUserStore.getState().token
export const getRefreshToken = () => useUserStore.getState().refreshToken
export const clearAuthState = () => useUserStore.getState().logout()
