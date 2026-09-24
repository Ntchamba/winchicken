import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

import { ACTION_LABELS } from "../auditActions";

// Every action code the backend writes must have a French label, or the audit journal shows it
// raw. Read from the backend source so a new record_audit_log call cannot drift past this map.
const BACKEND_APPS = join(__dirname, "../../../../backend/apps");

function pythonFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "migrations" || name === "__pycache__" ? [] : pythonFiles(path);
    return name.endsWith(".py") && !name.startsWith("tests") ? [path] : [];
  });
}

describe("audit action labels", () => {
  test("every record_audit_log code in the backend has a label", () => {
    const codes = new Set();
    for (const file of pythonFiles(BACKEND_APPS)) {
      for (const match of readFileSync(file, "utf8").matchAll(/record_audit_log\(\s*[^,]+,\s*'([a-z_.]+)'/g)) codes.add(match[1]);
    }
    expect(codes.size).toBeGreaterThan(10);
    expect([...codes].filter((code) => !ACTION_LABELS[code])).toEqual([]);
  });
});
