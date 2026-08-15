/**
 * PostgREST access.
 *
 * The API is deliberately unauthenticated: every auth requirement is a client
 * that will not connect, and this is public-record data published under CC0.
 * That posture only holds because the database enforces read-only access at the
 * row level — the anon key here can SELECT and nothing else.
 */
export interface Env {
  SUPABASE_URL: string;
  SUPABASE_ANON_KEY: string;
}

export class Db {
  constructor(private env: Env) {}

  private headers() {
    return {
      apikey: this.env.SUPABASE_ANON_KEY,
      authorization: `Bearer ${this.env.SUPABASE_ANON_KEY}`,
      accept: 'application/json',
      'content-type': 'application/json',
    };
  }

  async select<T>(path: string): Promise<T[]> {
    const res = await fetch(`${this.env.SUPABASE_URL}/rest/v1/${path}`, {
      headers: this.headers(),
      cf: { cacheTtl: 300, cacheEverything: true },
    });
    if (!res.ok) throw new HttpError(502, `upstream ${res.status}: ${await res.text()}`);
    return res.json();
  }

  /** Call a Postgres function. The resolver lives in the database, not here. */
  async rpc<T>(fn: string, args: Record<string, unknown>): Promise<T[]> {
    const res = await fetch(`${this.env.SUPABASE_URL}/rest/v1/rpc/${fn}`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(args),
    });
    if (!res.ok) throw new HttpError(502, `upstream ${res.status}: ${await res.text()}`);
    return res.json();
  }
}

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}
