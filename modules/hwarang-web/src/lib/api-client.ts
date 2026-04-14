/**
 * Typed API client for communicating with hwarang-api.
 */

const API_BASE = process.env.HWARANG_API_URL || "http://localhost:8000";

interface FetchOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {} } = options;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error ${response.status}: ${error}`);
  }

  return response.json();
}

export const apiClient = {
  /** List available models */
  listModels: () =>
    apiFetch<{ data: { id: string; object: string }[] }>("/v1/models"),

  /** Health check */
  health: () =>
    apiFetch<{ status: string; version: string; models_loaded: number }>("/health"),

  /** Create a streaming chat completion */
  chatStream: (body: {
    model: string;
    messages: { role: string; content: string }[];
    temperature?: number;
    max_tokens?: number;
  }) =>
    fetch(`${API_BASE}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, stream: true }),
    }),
};
