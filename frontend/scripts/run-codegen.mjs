#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const script = path.join(repoRoot, "scripts", "generate_ts_types.py");
const venvPy = path.join(repoRoot, ".venv", "bin", "python");
const py = process.env.PYTHON ?? (existsSync(venvPy) ? venvPy : "python3");

const result = spawnSync(py, [script], { cwd: repoRoot, stdio: "inherit", env: process.env });
process.exit(result.status ?? 1);
