// Turns a mission into a vector in the visitor's browser, off the main thread.
// Same model as grantmatch/embed.py (BAAI/bge-small-en-v1.5, CLS pooling, unit length); the fp16 ONNX
// export matches fastembed's vectors to within a tenth of a score point.
import { env, pipeline, type FeatureExtractionPipeline } from "@huggingface/transformers";

const MODEL = "Xenova/bge-small-en-v1.5";
let extractor: Promise<FeatureExtractionPipeline> | null = null;

function load(base: string) {
  if (!extractor) {
    // The deploy puts the model beside the site; without it, the Hugging Face hub serves the same files.
    env.localModelPath = `${base}models/`;
    env.allowLocalModels = true;
    env.allowRemoteModels = true;
    extractor = pipeline("feature-extraction", MODEL, {
      dtype: "fp16",
      device: "wasm",
      progress_callback: (p: { status: string; file?: string; loaded?: number; total?: number }) => {
        if (p.status === "progress" && p.file?.endsWith(".onnx")) {
          postMessage({ type: "progress", loaded: p.loaded ?? 0, total: p.total ?? 0 });
        }
      },
    }) as Promise<FeatureExtractionPipeline>;
    extractor.catch(() => { extractor = null; });
  }
  return extractor;
}

onmessage = async (e: MessageEvent<{ id: number; text: string; base: string }>) => {
  const { id, text, base } = e.data;
  try {
    const ext = await load(base);
    const out = await ext(text, { pooling: "cls", normalize: true });
    postMessage({ type: "vector", id, vector: Array.from(out.data as Float32Array) });
  } catch (err) {
    postMessage({ type: "error", id, message: err instanceof Error ? err.message : String(err) });
  }
};
