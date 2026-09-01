import { create } from 'zustand'
import type { UserInfo } from '../types/api'

interface UserState {
  userInfo: UserInfo | null
  token: string
  isLogin: boolean
  userBio: string
  login: (token: string, user: UserInfo) => void
  logout: () => void
  setUserInfo: (info: UserInfo) => void
  setToken: (token: string) => void
  setUserBio: (bio: string) => void
}

export const useUserStore = create<UserState>()((set) => ({
  userInfo: null,
  token: '',
  isLogin: false,
  userBio: '',
  login: (token, user) => set({ token, userInfo: user, isLogin: true }),
  logout: () => set({ token: '', userInfo: null, isLogin: false, userBio: '' }),
  setUserInfo: (info) => set({ userInfo: info }),
  setToken: (token) => set({ token, isLogin: Boolean(token) }),
  setUserBio: (bio) => set({ userBio: bio }),
}))

export const getAccessToken = () => useUserStore.getState().token
export const clearAuthState = () => useUserStore.getState().logout()
