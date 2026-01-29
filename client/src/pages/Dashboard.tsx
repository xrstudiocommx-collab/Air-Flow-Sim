import { useState } from "react";
import { useProjects, useCreateProject, useDeleteProject } from "@/hooks/use-projects";
import { Link } from "wouter";
import { Navbar } from "@/components/layout/Navbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2, ArrowRight, Wind, Clock } from "lucide-react";
import { format } from "date-fns";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// Create form schema
const createProjectFormSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
});

type CreateProjectFormValues = z.infer<typeof createProjectFormSchema>;

export default function Dashboard() {
  const { data: projects, isLoading } = useProjects();
  const createMutation = useCreateProject();
  const deleteMutation = useDeleteProject();
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const form = useForm<CreateProjectFormValues>({
    resolver: zodResolver(createProjectFormSchema),
    defaultValues: { name: "", description: "" }
  });

  const onSubmit = (values: CreateProjectFormValues) => {
    createMutation.mutate({
      name: values.name,
      description: values.description,
      // Default empty data structure
      data: {
        fans: [],
        obstacles: [],
        settings: {
          globalDecay: 2.0,
          resolution: 8,
          showHeatmap: true
        }
      }
    }, {
      onSuccess: () => {
        setIsCreateOpen(false);
        form.reset();
      }
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-display text-foreground mb-2">My Projects</h1>
            <p className="text-muted-foreground">Manage your airflow simulations and floor plans.</p>
          </div>
          
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button size="lg" className="gap-2 shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all">
                <Plus className="w-5 h-5" /> New Project
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>Create Project</DialogTitle>
                <DialogDescription>
                  Start a new simulation workspace. You can upload floor plans later.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Project Name</Label>
                  <Input 
                    id="name" 
                    placeholder="e.g. Office Ventilation Layout" 
                    {...form.register("name")} 
                  />
                  {form.formState.errors.name && (
                    <span className="text-sm text-destructive">{form.formState.errors.name.message}</span>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="desc">Description</Label>
                  <Textarea 
                    id="desc" 
                    placeholder="Optional project details..." 
                    {...form.register("description")} 
                  />
                </div>
                <DialogFooter>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? "Creating..." : "Create Project"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-48 rounded-xl bg-card border border-border animate-pulse" />
            ))}
          </div>
        ) : projects?.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center border-2 border-dashed border-border rounded-2xl bg-card/30">
            <div className="bg-secondary p-4 rounded-full mb-4">
              <Wind className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-xl font-semibold mb-2">No projects yet</h3>
            <p className="text-muted-foreground max-w-sm mb-6">
              Create your first project to start simulating airflow dynamics on your floor plans.
            </p>
            <Button onClick={() => setIsCreateOpen(true)} variant="outline">Create Project</Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects?.map((project) => (
              <Card key={project.id} className="group hover:border-primary/50 transition-all duration-300 hover:shadow-xl hover:shadow-primary/5">
                <CardHeader>
                  <CardTitle className="flex justify-between items-start">
                    <span className="truncate pr-2">{project.name}</span>
                    {project.data.backgroundImage && (
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-green-500/10 text-green-500 border border-green-500/20">
                        Has Plan
                      </span>
                    )}
                  </CardTitle>
                  <CardDescription className="line-clamp-2 min-h-[40px]">
                    {project.description || "No description provided."}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                    <div className="flex items-center gap-1">
                      <Wind className="w-3 h-3" />
                      {project.data.fans.length} Fans
                    </div>
                    <div className="flex items-center gap-1">
                      <Square className="w-3 h-3" />
                      {project.data.obstacles.length} Obstacles
                    </div>
                  </div>
                </CardContent>
                <CardFooter className="flex justify-between border-t border-border pt-4">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {project.createdAt && format(new Date(project.createdAt), 'MMM d, yyyy')}
                  </span>
                  
                  <div className="flex gap-2">
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      onClick={() => {
                        if (confirm("Are you sure you want to delete this project?")) {
                          deleteMutation.mutate(project.id);
                        }
                      }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                    <Link href={`/project/${project.id}`}>
                      <Button size="sm" className="gap-1 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                        Open <ArrowRight className="w-3 h-3" />
                      </Button>
                    </Link>
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
