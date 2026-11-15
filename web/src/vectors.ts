// Embedding rows are stored as little-endian float16, one row per id in vec_ids.

export interface VectorSet {
  ids: string[];
  dim: number;
  data: Float32Array; // ids.length * dim
}

function halfToFloat(h: number): number {
  const s = h & 0x8000 ? -1 : 1;
  const e = (h >> 10) & 0x1f;
  const f = h & 0x3ff;
  if (e === 0) return s * 2 ** -14 * (f / 1024);
  if (e === 31) return f ? NaN : s * Infinity;
  return s * 2 ** (e - 15) * (1 + f / 1024);
}

const TABLE = new Float32Array(65536);
for (let i = 0; i < 65536; i++) TABLE[i] = halfToFloat(i);

export function decodeF16(buf: ArrayBuffer, ids: string[], dim: number): VectorSet {
  const view = new DataView(buf);
  const n = buf.byteLength / 2;
  const data = new Float32Array(n);
  for (let i = 0; i < n; i++) data[i] = TABLE[view.getUint16(i * 2, true)];
  return { ids, dim, data };
}

/** Cosine similarity of every row with a unit query vector, by id. Rows are already unit length. */
export function similarities(set: VectorSet, query: ArrayLike<number>): Map<string, number> {
  const out = new Map<string, number>();
  const { dim, data } = set;
  for (let r = 0; r < set.ids.length; r++) {
    let s = 0;
    const o = r * dim;
    for (let k = 0; k < dim; k++) s += data[o + k] * query[k];
    out.set(set.ids[r], s);
  }
  return out;
}
