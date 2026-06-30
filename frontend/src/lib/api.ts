// Thin API client for the AgentOS backend. Day 1: domains only.

export interface Domain {
  id: string;
  user: string;
  slug: string;
  title: string;
  dataset_name: string;
}

const BASE = "/api/v1";

export async function listDomains(): Promise<Domain[]> {
  const res = await fetch(`${BASE}/domains`);
  if (!res.ok) throw new Error(`listDomains failed: ${res.status}`);
  return res.json();
}

export async function createDomain(slug: string, title: string): Promise<Domain> {
  const res = await fetch(`${BASE}/domains`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, title }),
  });
  if (!res.ok) throw new Error(`createDomain failed: ${res.status}`);
  return res.json();
}
