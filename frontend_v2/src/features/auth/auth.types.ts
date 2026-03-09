export interface User {
  username: string
  name: string
  role: string | null
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
