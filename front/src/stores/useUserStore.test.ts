import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearAuthState,
  getAccessToken,
  getRefreshToken,
  useUserStore,
} from './useUserStore'


const user = {
  id: 'user-1',
  username: 'alice',
  email: 'alice@example.com',
}


describe('useUserStore authentication state', () => {
  beforeEach(() => {
    localStorage.clear()
    useUserStore.setState({
      userInfo: null,
      token: '',
      refreshToken: '',
      isLogin: false,
      userBio: '',
    })
  })

  it('keeps the access and refresh tokens in one persisted store', () => {
    useUserStore.getState().login('access-1', user, 'refresh-1')

    expect(getAccessToken()).toBe('access-1')
    expect(getRefreshToken()).toBe('refresh-1')
    expect(useUserStore.getState().isLogin).toBe(true)
    expect(localStorage.getItem('jwt_token')).toBeNull()
  })

  it('rotates both tokens without losing the user state', () => {
    useUserStore.getState().login('access-1', user, 'refresh-1')
    useUserStore.getState().setTokens('access-2', 'refresh-2')

    expect(getAccessToken()).toBe('access-2')
    expect(getRefreshToken()).toBe('refresh-2')
    expect(useUserStore.getState().userInfo?.username).toBe('alice')
  })

  it('clears access, refresh and persisted login state together', () => {
    useUserStore.getState().login('access-1', user, 'refresh-1')

    clearAuthState()

    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
    expect(useUserStore.getState().userInfo).toBeNull()
    expect(useUserStore.getState().isLogin).toBe(false)
  })
})
