#!/usr/bin/env node
/**
 * Run scripts/generate_ts_types.py using backend/.venv when present, else python3.
 * Requires pydantic (install backend deps or `pip install pydantic`).
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "../..");
const venvPython = resolve(repoRoot, "backend/.venv/bin/python");
const fromEnv = (process.env.CODEGEN_PYTHON || "").trim();
const python =
  fromEnv || (existsSync(venvPython) ? venvPython : "python3");
const script = resolve(repoRoot, "scripts/generate_ts_types.py");
const result = spawnSync(python, [script], { stdio: "inherit", cwd: repoRoot });
process.exit(result.status === null ? 1 : result.status ?? 1);
