
import type { Express } from "express";
import type { Server } from "http";
import { storage } from "./storage";
import { api } from "@shared/routes";
import { z } from "zod";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // === PROJECTS API ===
  app.get(api.projects.list.path, async (_req, res) => {
    const projects = await storage.getProjects();
    res.json(projects);
  });

  app.get(api.projects.get.path, async (req, res) => {
    const project = await storage.getProject(Number(req.params.id));
    if (!project) {
      return res.status(404).json({ message: 'Project not found' });
    }
    res.json(project);
  });

  app.post(api.projects.create.path, async (req, res) => {
    try {
      const input = api.projects.create.input.parse(req.body);
      const project = await storage.createProject(input);
      res.status(201).json(project);
    } catch (err) {
      if (err instanceof z.ZodError) {
        return res.status(400).json({
          message: err.errors[0].message,
          field: err.errors[0].path.join('.'),
        });
      }
      throw err;
    }
  });

  app.put(api.projects.update.path, async (req, res) => {
    try {
      const input = api.projects.update.input.parse(req.body);
      const project = await storage.updateProject(Number(req.params.id), input);
      if (!project) {
        return res.status(404).json({ message: 'Project not found' });
      }
      res.json(project);
    } catch (err) {
      if (err instanceof z.ZodError) {
        return res.status(400).json({
          message: err.errors[0].message,
          field: err.errors[0].path.join('.'),
        });
      }
      throw err;
    }
  });

  app.delete(api.projects.delete.path, async (req, res) => {
    const existing = await storage.getProject(Number(req.params.id));
    if (!existing) {
      return res.status(404).json({ message: 'Project not found' });
    }
    await storage.deleteProject(Number(req.params.id));
    res.status(204).send();
  });

  // Seed data on startup
  await seedDefaults();

  return httpServer;
}

// Optional: Seed default project if empty
async function seedDefaults() {
  const existing = await storage.getProjects();
  if (existing.length === 0) {
    await storage.createProject({
      name: "Demo Office Layout",
      description: "Example simulation with open plan office",
      data: {
        fans: [
          { id: "f1", x: 200, y: 200, radius: 30, intensity: 100, decay: 0.005 }
        ],
        obstacles: [
          { id: "o1", points: [{ x: 300, y: 100 }, { x: 400, y: 100 }, { x: 400, y: 300 }, { x: 300, y: 300 }] }
        ],
        settings: {
          globalDecay: 0.005,
          resolution: 4,
          showHeatmap: true
        }
      }
    });
  }
}
