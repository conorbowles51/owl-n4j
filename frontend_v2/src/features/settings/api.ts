import { fetchAPI } from "@/lib/api-client"
import type { AIProviderConnection, AISettings, ProviderTestResult } from "./types"

export const aiSettingsAPI = {
  get: () => fetchAPI<AISettings>("/api/ai-settings"),
  saveCredential: (
    provider: string,
    apiKey: string,
    expectedRevision: number
  ) =>
    fetchAPI<AIProviderConnection>(
      `/api/ai-settings/providers/${provider}/credential`,
      {
        method: "PUT",
        body: { api_key: apiKey, expected_revision: expectedRevision },
      }
    ),
  testCredential: (provider: string) =>
    fetchAPI<ProviderTestResult>(`/api/ai-settings/providers/${provider}:test`, {
      method: "POST",
    }),
  disconnectCredential: (provider: string, expectedRevision: number) =>
    fetchAPI<void>(
      `/api/ai-settings/providers/${provider}/credential?expected_revision=${expectedRevision}`,
      { method: "DELETE" }
    ),
  updatePolicy: (
    revision: number,
    configuration: AISettings["routing"]
  ) =>
    fetchAPI<AISettings>("/api/ai-settings/policy", {
      method: "PUT",
      body: { revision, configuration },
    }),
}
