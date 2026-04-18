export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

/**
 * Standardized fetch utility to interact with the backend API Envelope
 * Expected backend shape:
 * { status: "success" | "error", data: any, message?: string }
 */
export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`
  
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const json = await response.json()
  
  // Unwrap the ApiResponse envelope if present
  if (json && typeof json === 'object' && ('status' in json || 'data' in json)) {
    if (json.status === 'error') {
      throw new Error(json.message || "API returned an error")
    }
    return json.data !== undefined ? json.data : json
  }

  // Healthchecks sometimes return raw data
  return json
}
