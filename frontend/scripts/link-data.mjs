#!/usr/bin/env node
import { existsSync, mkdirSync, symlinkSync, unlinkSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const target = resolve(__dirname, "../../data/local_pipeline");
const linkPath = resolve(__dirname, "../public/data");

const skip =
  process.env.SKIP_DATA_LINK === "1" ||
  process.env.SKIP_DATA_LINK === "true" ||
  process.env.SKIP_DATA_LINK === "yes";

mkdirSync(dirname(linkPath), { recursive: true });

if (skip) {
  console.warn("[link-data] SKIP_DATA_LINK set — not creating public/data symlink");
  process.exit(0);
}

if (!existsSync(target)) {
  console.error(
    `[link-data] target missing: ${target}\n` +
      "Create data/local_pipeline or set SKIP_DATA_LINK=1 for CI/typecheck-only builds.",
  );
  process.exit(1);
}

if (existsSync(linkPath)) {
  try {
    unlinkSync(linkPath);
  } catch (e) {
    // If it's a real directory (not a symlink), don't blow it away.
    console.warn(`[link-data] could not remove existing path: ${e?.message ?? e}`);
  }
}

const rel = relative(dirname(linkPath), target);
symlinkSync(rel, linkPath, "dir");
console.log(`[link-data] linked public/data -> ${rel}`);
