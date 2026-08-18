import axios, { type AxiosAdapter } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import client from './client'
import { useUserStore } from '../stores/useUserStore'

const originalAdapter = client.defaults.adapter

const unauthorized = (config: Parameters<AxiosAdapter>[0]) =>
  Promise.reject({ config, response: { status: 401 } })

describe('authentication response handling', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/login')
    localStorage.clear()
    useUserStore.setState({
      token: 'expired-access',
      refreshToken: 'refresh-1',
      userInfo: null,
      isLogin: true,
      userBio: 'private bio',
    })
  })

  afterEach(() => {
    client.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
  })

  it('deduplicates concurrent refreshes and retries both requests', async () => {
    const retriedAuthorizations: string[] = []
    client.defaults.adapter = (async (config) => {
      const authorization = String(config.headers?.Authorization || '')
      if (authorization !== 'Bearer fresh-access') return unauthorized(config)
      retriedAuthorizations.push(authorization)
      return {
        data: { ok: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }) as AxiosAdapter
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { token: 'fresh-access', refresh_token: 'refresh-2' },
    })

    const responses = await Promise.all([
      client.get('/protected/one'),
      client.get('/protected/two'),
    ])

    expect(responses.map((response) => response.status)).toEqual([200, 200])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(retriedAuthorizations).toEqual(['Bearer fresh-access', 'Bearer fresh-access'])
    expect(useUserStore.getState().token).toBe('fresh-access')
    expect(useUserStore.getState().refreshToken).toBe('refresh-2')
  })

  it('clears the complete auth state when refresh fails', async () => {
    client.defaults.adapter = (async (config) => unauthorized(config)) as AxiosAdapter
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('revocation store unavailable'))

    await expect(client.get('/protected')).rejects.toBeDefined()

    expect(useUserStore.getState()).toMatchObject({
      token: '',
      refreshToken: '',
      userInfo: null,
      isLogin: false,
      userBio: '',
    })
  })
})
