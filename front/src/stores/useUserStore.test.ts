import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearAuthState,
  getAccessToken,
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
      isLogin: false,
      userBio: '',
    })
  })

  it('keeps only the access token in memory', () => {
    useUserStore.getState().login('access-1', user)

    expect(getAccessToken()).toBe('access-1')
    expect(useUserStore.getState()).not.toHaveProperty('refreshToken')
    expect(useUserStore.getState().isLogin).toBe(true)
    expect(localStorage.getItem('jwt_token')).toBeNull()
  })

  it('rotates the access token without losing the user state', () => {
    useUserStore.getState().login('access-1', user)
    useUserStore.getState().setToken('access-2')

    expect(getAccessToken()).toBe('access-2')
    expect(useUserStore.getState().userInfo?.username).toBe('alice')
  })

  it('clears access and login state together', () => {
    useUserStore.getState().login('access-1', user)

    clearAuthState()

    expect(getAccessToken()).toBe('')
    expect(useUserStore.getState().userInfo).toBeNull()
    expect(useUserStore.getState().isLogin).toBe(false)
  })
})
