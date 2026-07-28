import { defineStore } from 'pinia'
import { getMe, login as apiLogin, logout as apiLogout } from '../api'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    initialized: false,
  }),
  actions: {
    async initialize() {
      if (this.initialized) return
      try {
        this.user = await getMe()
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async login(username: string, password: string) {
      this.user = await apiLogin(username, password)
      this.initialized = true
    },
    async logout() {
      try {
        await apiLogout()
      } finally {
        this.user = null
      }
    },
  },
})

