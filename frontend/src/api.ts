export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: unknown) {
    super(`HTTP ${status}`);
    this.name = 'ApiError';
  }
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function mutation(method: 'POST' | 'PUT', body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SommerauerMonitor' },
    body: JSON.stringify(body),
  };
}

export function diagnosticError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail;
    if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
      const code = 'code' in detail && typeof detail.code === 'string' ? ` (${detail.code})` : '';
      return `${detail.message}${code}`;
    }
    return `Die Diagnose-API meldet HTTP ${error.status}. Gespeicherte Belege bleiben erhalten.`;
  }
  return 'Die Diagnose-API ist nicht erreichbar. Der Ausgang der Aktion kann unklar sein. Zustand neu laden; die Aktion wird nicht automatisch wiederholt.';
}
