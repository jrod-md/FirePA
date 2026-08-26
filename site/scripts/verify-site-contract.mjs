import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = fileURLToPath(new URL("..", import.meta.url));
const repoRoot = resolve(siteRoot, "..");
const distRoot = resolve(siteRoot, "dist");
const publicRoot = resolve(repoRoot, "site-data");
const canonicalReport = resolve(repoRoot, "docs/FirePA_Scientific_Pilot_v1.pdf");
const builtReport = resolve(distRoot, "report.pdf");

if (!existsSync(distRoot)) throw new Error("Build output is missing: site/dist");

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const files = walk(distRoot).filter((path) => statSync(path).isFile());
const textFiles = files.filter((path) => !/\.(png|pdf)$/i.test(path));
const output = textFiles.map((path) => readFileSync(path, "utf8")).join("\n");
const requiredPages = [
  "index.html",
  "methodology/index.html",
  "sources/index.html",
  "es/index.html",
  "es/metodologia/index.html",
  "es/fuentes/index.html"
];

for (const page of requiredPages) {
  if (!existsSync(resolve(distRoot, page))) throw new Error(`Built route is missing: ${page}`);
}

if (!existsSync(canonicalReport)) throw new Error("Canonical scientific report is missing");
if (!existsSync(builtReport)) throw new Error("Built report route is missing: report.pdf");
if (readFileSync(builtReport).subarray(0, 5).toString("ascii") !== "%PDF-") {
  throw new Error("Built report route is not a PDF artifact");
}
if (sha256(builtReport) !== sha256(canonicalReport)) {
  throw new Error("Built report is not byte-identical to the canonical scientific report");
}

for (const value of [
  "1,532",
  "1,185",
  "611",
  "30",
  "28",
  "2",
  "r1500_t06",
  "CHAPTER 02",
  "CHAPTER 03",
  "CHAPTER 04",
  "CHAPTER 05",
  "CHAPTER 06",
  "CHAPTER 07",
  "SPATIAL_THRESHOLD_MISS",
  "72.733",
  "selected_pair",
  "window_median",
  "prefers-reduced-motion"
]) {
  if (!output.includes(value)) throw new Error(`Built output is missing required contract text: ${value}`);
}

const windowsSeparator = String.fromCharCode(92);
const forbidden = [
  `C:${windowsSeparator}Users${windowsSeparator}`,
  ["C:", "Users", ""].join("/"),
  "site-data/",
  "outputs/"
];
for (const value of forbidden) {
  if (output.includes(value)) throw new Error(`Built output contains forbidden content: ${value}`);
}

const englishHome = readFileSync(resolve(distRoot, "index.html"), "utf8");
const englishMethodology = readFileSync(resolve(distRoot, "methodology/index.html"), "utf8");
const englishSources = readFileSync(resolve(distRoot, "sources/index.html"), "utf8");
const spanishHome = readFileSync(resolve(distRoot, "es/index.html"), "utf8");
const spanishMethodology = readFileSync(resolve(distRoot, "es/metodologia/index.html"), "utf8");
const spanishSources = readFileSync(resolve(distRoot, "es/fuentes/index.html"), "utf8");

for (const document of [englishHome, englishMethodology, englishSources]) {
  for (const value of ['href="/report.pdf"', ">Report</a>", 'aria-label="Open scientific report (PDF)"']) {
    if (!document.includes(value)) throw new Error(`English route is missing report navigation: ${value}`);
  }
}

for (const document of [spanishHome, spanishMethodology, spanishSources]) {
  for (const value of ['href="/report.pdf"', ">Informe</a>", 'aria-label="Abrir informe científico (PDF)"']) {
    if (!document.includes(value)) throw new Error(`Spanish route is missing report navigation: ${value}`);
  }
}

for (const [document, expected] of [
  [englishHome, ['lang="en"', 'href="/es/"', "Can thermal signals"]],
  [spanishHome, ['lang="es"', 'href="/"', "¿Pueden las señales térmicas", "CAPÍTULO 07"]],
  [spanishMethodology, ['lang="es"', 'href="/methodology/"', "Metodología pública congelada"]],
  [spanishSources, ['lang="es"', 'href="/sources/"', "FUENTES / PROCEDENCIA"]]
]) {
  for (const value of expected) {
    if (!document.includes(value)) throw new Error(`Localized route is missing required text: ${value}`);
  }
}

const manifest = JSON.parse(readFileSync(resolve(publicRoot, "manifest.json"), "utf8"));
const figureChecks = manifest.files.filter((file) => file.path.startsWith("figures/")).map((file) => {
  const builtPath = resolve(distRoot, file.path);
  if (!existsSync(builtPath)) throw new Error(`Frozen figure is missing from build: ${file.path}`);
  const actualHash = sha256(builtPath);
  if (actualHash !== file.sha256) throw new Error(`Frozen figure hash changed in build: ${file.path}`);
  return file.path;
});

console.log(JSON.stringify({
  ok: true,
  files_checked: files.length,
  routes_checked: requiredPages,
  report_sha256: sha256(builtReport),
  frozen_figures_checked: figureChecks.length,
  public_contract: "English and Spanish Chapters 01–07 + methodology + sources + canonical report"
}, null, 2));
