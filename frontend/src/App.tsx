import { useEffect, useState } from "react";
import { createDomain, listDomains, type Domain } from "./lib/api";

// Day 1 dashboard shell: list domains + create a new one. The live run view,
// SSE feed, and BrainGraph land on Days 2-4.
export function App() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setDomains(await listDomains());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!slug || !title) return;
    try {
      await createDomain(slug, title);
      setSlug("");
      setTitle("");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>AgentOS</h1>
      <p style={{ color: "#666" }}>Multi-agent research platform · domain brains powered by Cognee</p>

      <form onSubmit={onCreate} style={{ display: "flex", gap: 8, margin: "1.5rem 0" }}>
        <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="slug (e.g. ai-safety)" />
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (e.g. AI Safety)" />
        <button type="submit">+ New Domain</button>
      </form>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        {domains.map((d) => (
          <article key={d.id} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
            <strong>{d.title}</strong>
            <div style={{ fontSize: 12, color: "#888" }}>{d.dataset_name}</div>
          </article>
        ))}
        {domains.length === 0 && <p style={{ color: "#999" }}>No domains yet. Create one above.</p>}
      </section>
    </main>
  );
}
