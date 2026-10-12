export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Workbench-Request': '1', ...init.headers },
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map(v => `${v.loc?.slice(1).join('.')}: ${v.msg}`).join('; ')
      : `Request failed (${response.status})`);
  }
  return body;
}

export function download(name: string, content: string | Blob, type = 'application/json') {
  const blob = typeof content === 'string' ? new Blob([content], { type }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function formatPrice(value: number | undefined, currency?: string) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: value < 10 ? 5 : 2,
    minimumFractionDigits: 2, ...(currency && currency.length === 3 ? { style: 'currency', currency } : {}) }).format(value);
}
