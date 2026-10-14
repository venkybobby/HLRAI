// Fails when src/api/schema.d.ts is stale relative to openapi/openapi.yaml (spec 6.1 rule 2).
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const out = join(mkdtempSync(join(tmpdir(), "hlrai-")), "schema.d.ts");
execFileSync("npx", ["openapi-typescript", "../openapi/openapi.yaml", "-o", out], { stdio: "ignore", shell: true });
if (readFileSync(out, "utf8") !== readFileSync("src/api/schema.d.ts", "utf8")) {
  console.error("src/api/schema.d.ts is out of date. Run: npm run gen:api");
  process.exit(1);
}
console.log("api types match the contract");
