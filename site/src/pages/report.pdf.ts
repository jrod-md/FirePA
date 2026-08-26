import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export const prerender = true;

const reportPath = fileURLToPath(
  new URL("../../../docs/FirePA_Scientific_Pilot_v1.pdf", import.meta.url)
);

export async function GET() {
  const report = await readFile(reportPath);

  return new Response(report, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'inline; filename="FirePA_Scientific_Pilot_v1.pdf"'
    }
  });
}
