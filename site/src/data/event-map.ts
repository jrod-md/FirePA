import presentationRaw from "./cocle-presentation.geojson?raw";
import { events, externalReferences, type PublicEventFeature, type ExternalReferenceFeature } from "./public";

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

export interface MappedEvent extends PublicEventFeature {
  x: number;
  y: number;
  statusClass: "observable" | "unobserved" | "not-in-cohort";
}

export interface MappedReference extends ExternalReferenceFeature {
  x: number;
  y: number;
  radiusX: number;
  radiusY: number;
}

export const EVENT_MAP_WIDTH = 1000;
export const EVENT_MAP_HEIGHT = 700;
const EVENT_MAP_PADDING = 64;
const METERS_PER_DEGREE_LATITUDE = 110540;
const METERS_PER_DEGREE_LONGITUDE = 111320;

const eventCoordinates = events.features.map((feature) => feature.geometry.coordinates);
const eventLongitudes = eventCoordinates.map(([longitude]) => longitude);
const eventLatitudes = eventCoordinates.map(([, latitude]) => latitude);
const rawMinLongitude = Math.min(...eventLongitudes);
const rawMaxLongitude = Math.max(...eventLongitudes);
const rawMinLatitude = Math.min(...eventLatitudes);
const rawMaxLatitude = Math.max(...eventLatitudes);
const longitudeSpan = rawMaxLongitude - rawMinLongitude;
const latitudeSpan = rawMaxLatitude - rawMinLatitude;
const longitudePadding = longitudeSpan * 0.08;
const latitudePadding = latitudeSpan * 0.08;
const minLongitude = rawMinLongitude - longitudePadding;
const maxLongitude = rawMaxLongitude + longitudePadding;
const minLatitude = rawMinLatitude - latitudePadding;
const maxLatitude = rawMaxLatitude + latitudePadding;
const paddedLongitudeSpan = maxLongitude - minLongitude;
const paddedLatitudeSpan = maxLatitude - minLatitude;
const drawableWidth = EVENT_MAP_WIDTH - EVENT_MAP_PADDING * 2;
const drawableHeight = EVENT_MAP_HEIGHT - EVENT_MAP_PADDING * 2;

function project([longitude, latitude]: Point): Point {
  return [
    EVENT_MAP_PADDING + ((longitude - minLongitude) / paddedLongitudeSpan) * drawableWidth,
    EVENT_MAP_HEIGHT - EVENT_MAP_PADDING - ((latitude - minLatitude) / paddedLatitudeSpan) * drawableHeight
  ];
}

function rounded(value: number): string {
  return value.toFixed(2);
}

function area(ring: Ring): number {
  return ring.slice(0, -1).reduce((total, point, index) => total + point[0] * ring[index + 1][1] - ring[index + 1][0] * point[1], 0) / 2;
}

function ringToPath(ring: Ring): string {
  return ring.map(project).map(([x, y], index) => `${index === 0 ? "M" : "L"}${rounded(x)} ${rounded(y)}`).join(" ") + " Z";
}

const boundary = JSON.parse(presentationRaw) as PresentationBoundary;
const polygons = boundary.features[0].geometry.coordinates;
const boundaryRings = polygons.flat();
const largestRing = boundaryRings.reduce((largest, ring) => (Math.abs(area(ring)) > Math.abs(area(largest)) ? ring : largest), boundaryRings[0]);
const labelPoint = project(meanPoint(largestRing));

function meanPoint(ring: Ring): Point {
  const openRing = ring.slice(0, -1);
  return [
    openRing.reduce((total, [longitude]) => total + longitude, 0) / openRing.length,
    openRing.reduce((total, [, latitude]) => total + latitude, 0) / openRing.length
  ];
}

export function mapStatusClass(status: MappedEvent["properties"]["optical_cohort_status"]): MappedEvent["statusClass"] {
  return status === "not_in_cohort" ? "not-in-cohort" : status;
}

export const mappedEvents: MappedEvent[] = events.features.map((feature) => {
  const [x, y] = project(feature.geometry.coordinates);
  return { ...feature, x, y, statusClass: mapStatusClass(feature.properties.optical_cohort_status) };
});

export const mappedReferences: MappedReference[] = externalReferences.features.map((feature) => {
  const [x, y] = project(feature.geometry.coordinates);
  const latitudeRadians = (feature.geometry.coordinates[1] * Math.PI) / 180;
  const radiusMeters = feature.properties.official_matching_radius_m;
  const radiusX = (radiusMeters / (METERS_PER_DEGREE_LONGITUDE * Math.cos(latitudeRadians))) / paddedLongitudeSpan * drawableWidth;
  const radiusY = (radiusMeters / METERS_PER_DEGREE_LATITUDE) / paddedLatitudeSpan * drawableHeight;
  return { ...feature, x, y, radiusX, radiusY };
});

export const cocleEventMap = {
  viewBox: `0 0 ${EVENT_MAP_WIDTH} ${EVENT_MAP_HEIGHT}`,
  path: boundaryRings.map(ringToPath).join(" "),
  labelPoint,
  eventCount: mappedEvents.length,
  derivedExtent: {
    minLongitude: rawMinLongitude,
    maxLongitude: rawMaxLongitude,
    minLatitude: rawMinLatitude,
    maxLatitude: rawMaxLatitude
  },
  padding: {
    longitude: longitudePadding,
    latitude: latitudePadding
  }
};
