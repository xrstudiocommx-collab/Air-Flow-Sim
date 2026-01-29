
import { pgTable, text, serial, jsonb, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// === DATA TYPES ===
// Stored in the 'data' JSONB column
export const fanSchema = z.object({
  id: z.string(),
  x: z.number(),
  y: z.number(),
  radius: z.number(), // Visual size
  intensity: z.number(), // Source strength
  decay: z.number(), // Falloff factor
});

export const obstacleSchema = z.object({
  id: z.string(),
  points: z.array(z.object({ x: z.number(), y: z.number() })),
});

export const projectDataSchema = z.object({
  fans: z.array(fanSchema),
  obstacles: z.array(obstacleSchema),
  backgroundImage: z.string().optional(), // Base64 or URL
  settings: z.object({
    globalDecay: z.number(),
    resolution: z.number(), // Simulation grid size
    showHeatmap: z.boolean(),
  }),
});

// === TABLE DEFINITIONS ===
export const projects = pgTable("projects", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  description: text("description"),
  data: jsonb("data").$type<z.infer<typeof projectDataSchema>>().notNull(),
  thumbnail: text("thumbnail"), // Optional preview image
  createdAt: timestamp("created_at").defaultNow(),
});

// === SCHEMAS ===
export const insertProjectSchema = createInsertSchema(projects);

// === API TYPES ===
export type Project = typeof projects.$inferSelect;
export type InsertProject = z.infer<typeof insertProjectSchema>;
export type ProjectData = z.infer<typeof projectDataSchema>;
export type Fan = z.infer<typeof fanSchema>;
export type Obstacle = z.infer<typeof obstacleSchema>;
