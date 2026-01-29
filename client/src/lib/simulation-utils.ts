import { type Fan, type Obstacle } from "@shared/schema";
import { scaleLinear } from "d3-scale";
import { interpolateTurbo } from "d3-interpolate";

// Basic geometry types
interface Point { x: number; y: number; }
interface Segment { p1: Point; p2: Point; }

// --- HEATMAP UTILS ---

export const colorScale = scaleLinear<string>()
  .domain([0, 1])
  .range(["rgba(0,0,0,0)", "rgba(255, 50, 50, 0.6)"]); // Simple gradient, or use D3 interpolate

// Get color from intensity value (0 to 1)
export function getHeatmapColor(value: number): string {
  if (value < 0.05) return "transparent";
  // Use Turbo colormap which is excellent for scientific visualization
  // We add alpha to make it overlay nicely
  const color = interpolateTurbo(value);
  // Convert rgb(...) to rgba(..., 0.5) roughly
  return color.replace("rgb", "rgba").replace(")", ", 0.5)");
}

// --- GEOMETRY UTILS ---

// Check if line segment AB intersects line segment CD
function segmentsIntersect(a: Point, b: Point, c: Point, d: Point): boolean {
  const det = (b.x - a.x) * (d.y - c.y) - (d.x - c.x) * (b.y - a.y);
  if (det === 0) return false;
  
  const lambda = ((d.y - c.y) * (d.x - a.x) + (c.x - d.x) * (d.y - a.y)) / det;
  const gamma = ((a.y - b.y) * (d.x - a.x) + (b.x - a.x) * (d.y - a.y)) / det;
  
  return (0 < lambda && lambda < 1) && (0 < gamma && gamma < 1);
}

// Check if a point is inside a polygon (Ray casting algorithm)
export function isPointInPolygon(point: Point, polygonPoints: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygonPoints.length - 1; i < polygonPoints.length; j = i++) {
    const xi = polygonPoints[i].x, yi = polygonPoints[i].y;
    const xj = polygonPoints[j].x, yj = polygonPoints[j].y;
    
    const intersect = ((yi > point.y) !== (yj > point.y))
        && (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// Check if there is a line of sight between Source and Target blocked by Obstacles
export function hasLineOfSight(source: Point, target: Point, obstacles: Obstacle[]): boolean {
  for (const obs of obstacles) {
    // Check intersection with each edge of the polygon
    for (let i = 0; i < obs.points.length; i++) {
      const p1 = obs.points[i];
      const p2 = obs.points[(i + 1) % obs.points.length];
      
      if (segmentsIntersect(source, target, p1, p2)) {
        return false;
      }
    }
    
    // Also check if target is INSIDE an obstacle (should have 0 flow)
    if (isPointInPolygon(target, obs.points)) {
      return false;
    }
  }
  return true;
}

// Calculate airflow intensity at a point
export function calculateIntensityAtPoint(
  point: Point,
  fans: Fan[],
  obstacles: Obstacle[],
  globalDecay: number
): number {
  let totalIntensity = 0;

  // Optimization: Check if point is inside any obstacle first
  for (const obs of obstacles) {
    if (isPointInPolygon(point, obs.points)) return 0;
  }

  for (const fan of fans) {
    const dx = point.x - fan.x;
    const dy = point.y - fan.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // Basic physics: Inverse square law or Exponential decay
    // Using exponential as requested: I = I0 * e^(-decay * dist)
    // Scale distance to reasonable units (e.g., pixels / 100)
    const effectiveDecay = (fan.decay * globalDecay) / 1000; 
    const contribution = fan.intensity * Math.exp(-effectiveDecay * dist);

    if (contribution > 0.01) { // Only check LOS if contribution is significant
      if (hasLineOfSight({ x: fan.x, y: fan.y }, point, obstacles)) {
        totalIntensity += contribution;
      }
    }
  }

  // Cap at 1.0
  return Math.min(totalIntensity, 1.0);
}
