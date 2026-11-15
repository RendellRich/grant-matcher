// Puts the matching model beside the site (public/models), so visitors load it from the same host.
// Pinned to one revision of Xenova/bge-small-en-v1.5; the parity test in test/ was run against it.
import { createWriteStream, existsSync, mkdirSync, copyFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const REPO = "Xenova/bge-small-en-v1.5";
const REVISION = "ea104dacec62c0de699686887e3f920caeb4f3e3";
const FILES = ["config.json", "tokenizer.json", "tokenizer_config.json", "onnx/model_fp16.onnx"];
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const out = join(root, "public", "models", REPO);
const cache = join(root, "node_modules", "@huggingface", "transformers", ".cache", REPO);

for (const f of FILES) {
  const dest = join(out, f);
  if (existsSync(dest) && statSync(dest).size > 0) continue;
  mkdirSync(dirname(dest), { recursive: true });
  if (existsSync(join(cache, f))) {
    copyFileSync(join(cache, f), dest);
    console.log(`copied ${f} from the local cache`);
    continue;
  }
  const url = `https://huggingface.co/${REPO}/resolve/${REVISION}/${f}`;
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`${url}: ${res.status}`);
  await pipeline(Readable.fromWeb(res.body), createWriteStream(dest));
  console.log(`downloaded ${f}`);
}
