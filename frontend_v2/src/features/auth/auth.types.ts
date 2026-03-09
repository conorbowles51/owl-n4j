export interface User {
  id?: string
  email?: string
  username: string
  name: string
  role: string | null
  global_role?: string
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  username: string
  name: string
  role: string | null
}

export interface AuthState {
  isAuthenticated: boolean
  user: User | null
  token: string | null
}
