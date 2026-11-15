// Main-thread side of the embedding worker. One request at a time; the newest wins.
export type ModelProgress = { loaded: number; total: number };

let worker: Worker | null = null;
let next = 0;
const waiting = new Map<number, { resolve: (v: number[]) => void; reject: (e: Error) => void }>();
let onProgress: ((p: ModelProgress) => void) | null = null;

function ensure(): Worker {
  if (!worker) {
    worker = new Worker(new URL("./embed-worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === "progress") onProgress?.({ loaded: m.loaded, total: m.total });
      else {
        const w = waiting.get(m.id);
        waiting.delete(m.id);
        if (m.type === "vector") w?.resolve(m.vector);
        else w?.reject(new Error(m.message));
      }
    };
  }
  return worker;
}

export function embedMission(text: string, progress: (p: ModelProgress) => void): Promise<number[]> {
  onProgress = progress;
  const id = ++next;
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    ensure().postMessage({ id, text, base: new URL(import.meta.env.BASE_URL, location.href).href });
  });
}
