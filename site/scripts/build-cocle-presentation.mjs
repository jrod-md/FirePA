import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = resolve(siteRoot, "..", "data", "reference", "cocle.geojson");
const outputPath = resolve(siteRoot, "src", "data", "cocle-presentation.geojson");
const sourceExists = existsSync(sourcePath);
const EXPECTED_POLYGON_COUNT = 5;

// The local boundary source is intentionally not redistributed. A clean public
// clone validates the tracked presentation derivative instead of regenerating
// it; a research checkout with the source present keeps deterministic rebuilds.

// Prefer the higher-fidelity candidate for crisp SVG rendering, while keeping
// deterministic fallbacks if a tighter tolerance exposes a topology issue.
const TOLERANCE_CANDIDATES = [0.00014, 0.00022, 0.00035, 0.00009, 0.00005];

function squaredDistanceToSegment(point, first, second) {
  const dx = second[0] - first[0];
  const dy = second[1] - first[1];
  if (dx === 0 && dy === 0) {
    return (point[0] - first[0]) ** 2 + (point[1] - first[1]) ** 2;
  }
  const t = Math.max(0, Math.min(1, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / (dx * dx + dy * dy)));
  const projection = [first[0] + t * dx, first[1] + t * dy];
  return (point[0] - projection[0]) ** 2 + (point[1] - projection[1]) ** 2;
}

function simplifyOpenRing(points, tolerance, requiredIndexes) {
  if (points.length <= 3) return points.slice();

  const squaredTolerance = tolerance ** 2;
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;
  for (const index of requiredIndexes) keep[index] = 1;

  const stack = [[0, points.length - 1]];
  while (stack.length > 0) {
    const [start, end] = stack.pop();
    let farthestIndex = -1;
    let farthestDistance = squaredTolerance;
    for (let index = start + 1; index < end; index += 1) {
      const distance = squaredDistanceToSegment(points[index], points[start], points[end]);
      if (distance > farthestDistance) {
        farthestDistance = distance;
        farthestIndex = index;
      }
    }
    if (farthestIndex !== -1) {
      keep[farthestIndex] = 1;
      stack.push([start, farthestIndex], [farthestIndex, end]);
    }
  }

  return points.filter((_, index) => keep[index] === 1);
}

function ringArea(ring) {
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    area += ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1];
  }
  return area / 2;
}

function orientation(first, second, third) {
  return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0]);
}

function onSegment(point, first, second) {
  return (
    Math.abs(orientation(first, second, point)) <= 1e-10 &&
    point[0] >= Math.min(first[0], second[0]) - 1e-10 &&
    point[0] <= Math.max(first[0], second[0]) + 1e-10 &&
    point[1] >= Math.min(first[1], second[1]) - 1e-10 &&
    point[1] <= Math.max(first[1], second[1]) + 1e-10
  );
}

function segmentsIntersect(first, second, third, fourth) {
  const values = [
    orientation(first, second, third),
    orientation(first, second, fourth),
    orientation(third, fourth, first),
    orientation(third, fourth, second)
  ];
  if (values.every((value) => Math.abs(value) <= 1e-10)) {
    return [first, second, third, fourth].some((point) => onSegment(point, first, second) && onSegment(point, third, fourth));
  }
  return ((values[0] > 0) !== (values[1] > 0)) && ((values[2] > 0) !== (values[3] > 0));
}

function bbox(ring) {
  const xs = ring.map(([x]) => x);
  const ys = ring.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function bboxesOverlap(first, second) {
  return !(first[2] < second[0] || second[2] < first[0] || first[3] < second[1] || second[3] < first[1]);
}

function validateRing(ring) {
  if (ring.length < 4 || ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1] || Math.abs(ringArea(ring)) <= 1e-12) {
    return false;
  }
  const segments = ring.slice(0, -1).map((point, index) => ({
    first: point,
    second: ring[index + 1],
    bounds: bbox([point, ring[index + 1]])
  }));
  for (let firstIndex = 0; firstIndex < segments.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < segments.length; secondIndex += 1) {
      if (secondIndex === firstIndex + 1 || (firstIndex === 0 && secondIndex === segments.length - 1)) continue;
      const first = segments[firstIndex];
      const second = segments[secondIndex];
      if (bboxesOverlap(first.bounds, second.bounds) && segmentsIntersect(first.first, first.second, second.first, second.second)) return false;
    }
  }
  return true;
}

function requiredExtrema(points) {
  const indexes = new Set();
  for (const comparator of [
    (first, second) => first[0] < second[0],
    (first, second) => first[0] > second[0],
    (first, second) => first[1] < second[1],
    (first, second) => first[1] > second[1]
  ]) {
    let selected = 0;
    for (let index = 1; index < points.length; index += 1) {
      if (comparator(points[index], points[selected])) selected = index;
    }
    indexes.add(selected);
  }
  return indexes;
}

function simplifyRing(ring, tolerance) {
  const openRing = ring.slice(0, -1);
  const simplified = simplifyOpenRing(openRing, tolerance, requiredExtrema(openRing));
  const closed = [...simplified, simplified[0]];
  return closed.length >= 4 ? closed : ring.slice();
}

function countPoints(polygons) {
  return polygons.reduce((total, polygon) => total + polygon.reduce((polygonTotal, ring) => polygonTotal + ring.length, 0), 0);
}

function bounds(polygons) {
  const points = polygons.flat(2);
  return [
    Math.min(...points.map(([x]) => x)),
    Math.min(...points.map(([, y]) => y)),
    Math.max(...points.map(([x]) => x)),
    Math.max(...points.map(([, y]) => y))
  ];
}

function totalArea(polygons) {
  return polygons.reduce((total, polygon) => total + polygon.reduce((polygonTotal, ring, ringIndex) => {
    const signed = Math.abs(ringArea(ring));
    return polygonTotal + (ringIndex === 0 ? signed : -signed);
  }, 0), 0);
}

function validateTopology(original, simplified) {
  if (original.length !== simplified.length) return false;
  for (let polygonIndex = 0; polygonIndex < original.length; polygonIndex += 1) {
    if (original[polygonIndex].length !== simplified[polygonIndex].length) return false;
    for (let ringIndex = 0; ringIndex < simplified[polygonIndex].length; ringIndex += 1) {
      if (!validateRing(simplified[polygonIndex][ringIndex])) return false;
    }
  }

  const outerRings = simplified.map((polygon) => polygon[0]);
  for (let firstIndex = 0; firstIndex < outerRings.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < outerRings.length; secondIndex += 1) {
      const first = outerRings[firstIndex];
      const second = outerRings[secondIndex];
      if (bboxesOverlap(bbox(first), bbox(second))) {
        for (let firstSegment = 0; firstSegment < first.length - 1; firstSegment += 1) {
          for (let secondSegment = 0; secondSegment < second.length - 1; secondSegment += 1) {
            if (segmentsIntersect(first[firstSegment], first[firstSegment + 1], second[secondSegment], second[secondSegment + 1])) return false;
          }
        }
      }
    }
  }
  return true;
}

function validatePresentationGeometry(candidate, label) {
  const geometry = candidate?.features?.[0]?.geometry;
  if (candidate?.type !== "FeatureCollection" || candidate?.features?.length !== 1 || geometry?.type !== "MultiPolygon") {
    throw new Error(`${label} must be one FeatureCollection with one MultiPolygon feature.`);
  }

  const polygons = geometry.coordinates;
  if (!Array.isArray(polygons) || polygons.length !== EXPECTED_POLYGON_COUNT) {
    throw new Error(`${label} must contain exactly ${EXPECTED_POLYGON_COUNT} polygons.`);
  }
  if (!validateTopology(polygons, polygons)) {
    throw new Error(`${label} failed the deterministic ring/topology validation.`);
  }

  return {
    polygonCount: polygons.length,
    pointCount: countPoints(polygons),
    bounds: bounds(polygons)
  };
}

if (!sourceExists) {
  if (!existsSync(outputPath)) {
    throw new Error(`Missing required public presentation artifact: ${outputPath}`);
  }

  const derivative = JSON.parse(readFileSync(outputPath, "utf8"));
  const derivativeSummary = validatePresentationGeometry(derivative, "Tracked Coclé presentation derivative");
  console.log(JSON.stringify({
    source: "data/reference/cocle.geojson (not present; local regeneration skipped)",
    source_available: false,
    derivative: "src/data/cocle-presentation.geojson",
    derivative_polygons: derivativeSummary.polygonCount,
    derivative_points: derivativeSummary.pointCount,
    topology_valid: true,
    artifact_present: true,
    mode: "validated tracked derivative"
  }, null, 2));
  process.exit(0);
}

const source = JSON.parse(readFileSync(sourcePath, "utf8"));
const sourceGeometry = source?.features?.[0]?.geometry;
if (source?.type !== "FeatureCollection" || source?.features?.length !== 1 || sourceGeometry?.type !== "MultiPolygon") {
  throw new Error("Expected the approved Coclé boundary to be one MultiPolygon feature.");
}
if (sourceGeometry.coordinates.length !== EXPECTED_POLYGON_COUNT) {
  throw new Error(`Expected the approved Coclé boundary to contain exactly ${EXPECTED_POLYGON_COUNT} polygons.`);
}
validatePresentationGeometry(source, "Local Coclé source boundary");

let selectedTolerance = null;
let simplifiedCoordinates = null;
for (const tolerance of TOLERANCE_CANDIDATES) {
  const candidate = sourceGeometry.coordinates.map((polygon) => polygon.map((ring) => simplifyRing(ring, tolerance)));
  if (validateTopology(sourceGeometry.coordinates, candidate)) {
    selectedTolerance = tolerance;
    simplifiedCoordinates = candidate;
    break;
  }
}

if (!simplifiedCoordinates || selectedTolerance === null) {
  throw new Error("Could not produce a valid presentation derivative without breaking ring topology.");
}

const sourceBounds = bounds(sourceGeometry.coordinates);
const derivativeBounds = bounds(simplifiedCoordinates);
const areaRelativeDifference = Math.abs(totalArea(sourceGeometry.coordinates) - totalArea(simplifiedCoordinates)) / totalArea(sourceGeometry.coordinates);
if (sourceBounds.some((value, index) => Math.abs(value - derivativeBounds[index]) > 1e-10)) {
  throw new Error("The presentation derivative changed the source boundary extent.");
}
if (areaRelativeDifference > 0.01) {
  throw new Error(`The presentation derivative changed area by ${(areaRelativeDifference * 100).toFixed(3)}%.`);
}

const derivative = {
  type: "FeatureCollection",
  name: "cocle_boundary_presentation_v1",
  crs: source.crs,
  features: [
    {
      type: "Feature",
      properties: {
        _presentation_only: true,
        _source_boundary: "data/reference/cocle.geojson",
        _simplification_method: "Ramer-Douglas-Peucker per source ring with deterministic extrema retention",
        _simplification_tolerance_degrees: selectedTolerance
      },
      geometry: {
        type: "MultiPolygon",
        coordinates: simplifiedCoordinates
      }
    }
  ]
};

const derivativeSummary = validatePresentationGeometry(derivative, "Generated Coclé presentation derivative");
let existingDerivativeMatches = false;
if (existsSync(outputPath)) {
  try {
    const existingDerivative = JSON.parse(readFileSync(outputPath, "utf8"));
    existingDerivativeMatches = JSON.stringify(existingDerivative) === JSON.stringify(derivative);
  } catch {
    existingDerivativeMatches = false;
  }
}
if (!existingDerivativeMatches) {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${JSON.stringify(derivative, null, 2)}\n`, "utf8");
}

console.log(JSON.stringify({
  source: "data/reference/cocle.geojson",
  source_polygons: sourceGeometry.coordinates.length,
  source_points: countPoints(sourceGeometry.coordinates),
  derivative: "src/data/cocle-presentation.geojson",
  derivative_polygons: derivativeSummary.polygonCount,
  derivative_points: derivativeSummary.pointCount,
  tolerance_degrees: selectedTolerance,
  topology_valid: true,
  bbox_preserved: true,
  area_relative_difference: areaRelativeDifference,
  derivative_reused: existingDerivativeMatches
}, null, 2));
