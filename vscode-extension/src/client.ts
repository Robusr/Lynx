/** Thin HTTP client for the SDK's FastAPI demo server. */

export interface LynxState {
  backend: string;
  running: boolean;
  has_frame: boolean;
  error?: string;
  latency_threshold_ms?: number;
}

export interface LynxMetrics {
  frames: number;
  fps: number;
  backend: string;
  latency_ms: { last: number; avg: number; p95: number; max: number };
  objects: { last: number; sources: Record<string, number> };
  traffic_signs_last: number;
}

export class LynxClient {
  constructor(private readonly origin: string) {}

  async state(): Promise<LynxState> {
    const res = await fetch(`${this.origin}/api/state`);
    return (await res.json()) as LynxState;
  }

  async metrics(): Promise<LynxMetrics> {
    const res = await fetch(`${this.origin}/api/metrics`);
    return (await res.json()) as LynxMetrics;
  }

  async switchBackend(backend: string): Promise<void> {
    const res = await fetch(`${this.origin}/api/switch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend }),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as { detail?: string; error?: string };
        detail = body.detail ?? body.error ?? detail;
      } catch {
        // keep the HTTP status text
      }
      throw new Error(detail);
    }
  }
}
