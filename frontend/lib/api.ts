import type {
  PortfolioStats,
  ScreeningDossier,
  TopOrgRow,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    const err = new Error(`${res.status} ${detail}`) as Error & {
      status: number;
    };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export async function getTopOrgs(limit = 200): Promise<TopOrgRow[]> {
  return request<TopOrgRow[]>(`/api/orgs/top?limit=${limit}`);
}

export async function searchOrgs(q: string): Promise<TopOrgRow[]> {
  return request<TopOrgRow[]>(
    `/api/orgs/search?q=${encodeURIComponent(q)}&limit=25`
  );
}

export async function getOrg(id: string): Promise<ScreeningDossier> {
  return request<ScreeningDossier>(`/api/orgs/${encodeURIComponent(id)}`);
}

export async function screenOrg(id: string): Promise<ScreeningDossier> {
  return request<ScreeningDossier>(
    `/api/orgs/${encodeURIComponent(id)}/screen`,
    { method: "POST" }
  );
}

export async function screenByName(name: string): Promise<ScreeningDossier> {
  return request<ScreeningDossier>("/api/screen/by-name", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function getPortfolioStats(): Promise<PortfolioStats | null> {
  try {
    return await request<PortfolioStats>("/api/portfolio/stats");
  } catch (e) {
    if ((e as { status?: number }).status === 404) return null;
    throw e;
  }
}

export const API_BASE_URL = API_BASE;
