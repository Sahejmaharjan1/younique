import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = json.loads((root / "openapi.json").read_text())
paths = sorted(spec.get("paths", {}))
lines = [
    "export const paths = [",
    *[f"  {json.dumps(path)}," for path in paths],
    "] as const;",
    "",
    "export type Problem = {",
    "  type: string;",
    "  title: string;",
    "  status: number;",
    "  code: string;",
    "  retryable: boolean;",
    "  request_id: string;",
    "  detail?: string;",
    "};",
    "",
    "export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {",
    "  return fetch(path, { credentials: 'include', ...init });",
    "}",
    "",
]
target = root / "packages" / "api-client" / "src" / "index.ts"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("\n".join(lines))
print(target)
