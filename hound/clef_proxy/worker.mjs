// Local-only CLEF proxy for Hound. Run with `hound clef serve`; never deploy it.
// It forwards a SystemOne request to Workers AI through the account you signed in to.
const MODELS = new Set(["clef", "clef-flash"]);

export default {
  async fetch(request, env) {
    const host = new URL(request.url).hostname;
    if (!["127.0.0.1", "localhost", "[::1]"].includes(host)) {
      return Response.json({ error: "local_only" }, { status: 403 });
    }
    if (request.method !== "POST") return Response.json({ error: "post_required" }, { status: 405 });
    const input = await request.json().catch(() => null);
    const model = input?.model ?? "clef";
    if (!MODELS.has(model)) return Response.json({ error: "invalid_model" }, { status: 400 });
    try {
      const result = await env.AI.run(`@cf/cloudflare/${model}`, { ...input, model });
      return Response.json({ result });
    } catch (error) {
      const message = error instanceof Error ? error.message.slice(0, 300) : "unknown";
      return Response.json({ error: "workers_ai_error", message }, { status: 502 });
    }
  },
};
