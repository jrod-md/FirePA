import presentationRaw from "./cocle-presentation.geojson?raw";

type Point = [number, number];
type Ring = Point[];
type Polygon = Ring[];

interface PresentationBoundary {
  features: Array<{
    geometry: {
      type: "MultiPolygon";
      coordinates: Polygon[];
    };
  }>;
}

const DISPLAY_WIDTH = 1200;
const DISPLAY_HEIGHT = 920;
const DISPLAY_PADDING = 78;
// This is a presentation-only cartographic derivative of
// data/reference/cocle.geojson, embedded at build time for a static SVG.
const boundary = JSON.parse(presentationRaw) as PresentationBoundary;
const polygons = boundary.features[0].geometry.coordinates;
const rings = polygons.flat();
const points = rings.flat();
const minLongitude = Math.min(...points.map(([longitude]) => longitude));
const maxLongitude = Math.max(...points.map(([longitude]) => longitude));
const minLatitude = Math.min(...points.map(([, latitude]) => latitude));
const maxLatitude = Math.max(...points.map(([, latitude]) => latitude));
const longitudeSpan = maxLongitude - minLongitude;
const latitudeSpan = maxLatitude - minLatitude;
const scale = Math.min(
  (DISPLAY_WIDTH - DISPLAY_PADDING * 2) / longitudeSpan,
  (DISPLAY_HEIGHT - DISPLAY_PADDING * 2) / latitudeSpan
);
const horizontalOffset = (DISPLAY_WIDTH - longitudeSpan * scale) / 2;
const verticalOffset = (DISPLAY_HEIGHT - latitudeSpan * scale) / 2;

function project([longitude, latitude]: Point): Point {
  return [
    horizontalOffset + (longitude - minLongitude) * scale,
    DISPLAY_HEIGHT - (verticalOffset + (latitude - minLatitude) * scale)
  ];
}

function rounded(value: number): string {
  return value.toFixed(2);
}

function ringToPath(ring: Ring): string {
  const projected = ring.map(project);
  return projected.map(([x, y], index) => `${index === 0 ? "M" : "L"}${rounded(x)} ${rounded(y)}`).join(" ") + " Z";
}

const largestRing = rings.reduce((largest, ring) => (Math.abs(area(ring)) > Math.abs(area(largest)) ? ring : largest), rings[0]);
const labelPoint = project(meanPoint(largestRing));

function area(ring: Ring): number {
  return ring.slice(0, -1).reduce((total, point, index) => total + point[0] * ring[index + 1][1] - ring[index + 1][0] * point[1], 0) / 2;
}

function meanPoint(ring: Ring): Point {
  const openRing = ring.slice(0, -1);
  return [
    openRing.reduce((total, [longitude]) => total + longitude, 0) / openRing.length,
    openRing.reduce((total, [, latitude]) => total + latitude, 0) / openRing.length
  ];
}

export const cocleCartography = {
  viewBox: `0 0 ${DISPLAY_WIDTH} ${DISPLAY_HEIGHT}`,
  path: rings.map(ringToPath).join(" "),
  labelPoint,
  polygonCount: polygons.length,
  pointCount: points.length,
  provenance: "Presentation-only cartographic derivative of data/reference/cocle.geojson"
};
