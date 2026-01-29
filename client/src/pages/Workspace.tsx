import { useEffect, useState } from "react";
import { useRoute, useLocation } from "wouter";
import { useProject, useUpdateProject } from "@/hooks/use-projects";
import { SimulationCanvas } from "@/components/workspace/SimulationCanvas";
import { Navbar } from "@/components/layout/Navbar";
import { ToolButton } from "@/components/ui/ToolButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { 
  MousePointer2, 
  Fan as FanIcon, 
  Square, 
  Save, 
  Download, 
  Upload, 
  Loader2,
  ArrowLeft,
  Settings as SettingsIcon
} from "lucide-react";
import { ProjectData } from "@shared/schema";
import { useToast } from "@/hooks/use-toast";

export default function Workspace() {
  const [match, params] = useRoute("/project/:id");
  const projectId = params ? parseInt(params.id) : 0;
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const { data: project, isLoading } = useProject(projectId);
  const updateMutation = useUpdateProject();

  // Local state for workspace
  const [projectData, setProjectData] = useState<ProjectData | null>(null);
  const [activeTool, setActiveTool] = useState<'select' | 'fan' | 'obstacle'>('select');
  const [isDirty, setIsDirty] = useState(false);

  // Sync data when loaded
  useEffect(() => {
    if (project) {
      setProjectData(project.data);
    }
  }, [project]);

  // Handle saving
  const handleSave = () => {
    if (!projectData) return;
    updateMutation.mutate({ 
      id: projectId, 
      data: projectData 
    }, {
      onSuccess: () => {
        setIsDirty(false);
        toast({ title: "Saved", description: "Project simulation data saved." });
      }
    });
  };

  // Handle file upload (Background Plan)
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && projectData) {
      const reader = new FileReader();
      reader.onload = (evt) => {
        const result = evt.target?.result as string;
        setProjectData({ ...projectData, backgroundImage: result });
        setIsDirty(true);
      };
      reader.readAsDataURL(file);
    }
  };

  // Handle setting changes
  const updateSetting = <K extends keyof ProjectData['settings']>(
    key: K, 
    value: ProjectData['settings'][K]
  ) => {
    if (!projectData) return;
    setProjectData({
      ...projectData,
      settings: { ...projectData.settings, [key]: value }
    });
    setIsDirty(true);
  };

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <span className="ml-2 font-medium text-muted-foreground">Loading workspace...</span>
      </div>
    );
  }

  if (!project || !projectData) {
    return <div>Project not found</div>;
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <Navbar />
      
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar Tools */}
        <aside className="w-72 bg-card border-r border-border flex flex-col z-10 shadow-xl">
          <div className="p-4 border-b border-border">
            <div className="flex items-center gap-2 mb-2">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-8 w-8 -ml-2"
                onClick={() => setLocation("/")}
              >
                <ArrowLeft className="w-4 h-4" />
              </Button>
              <h2 className="font-semibold truncate" title={project.name}>{project.name}</h2>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2">{project.description}</p>
          </div>

          <div className="p-4 grid grid-cols-3 gap-2">
            <ToolButton 
              active={activeTool === 'select'} 
              onClick={() => setActiveTool('select')} 
              icon={MousePointer2} 
              label="Select" 
            />
            <ToolButton 
              active={activeTool === 'fan'} 
              onClick={() => setActiveTool('fan')} 
              icon={FanIcon} 
              label="Add Fan" 
            />
            <ToolButton 
              active={activeTool === 'obstacle'} 
              onClick={() => setActiveTool('obstacle')} 
              icon={Square} 
              label="Obstacle" 
            />
          </div>

          <Separator />

          <div className="p-4 space-y-6 flex-1 overflow-y-auto">
            {/* Simulation Settings */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <SettingsIcon className="w-4 h-4" /> Simulation Params
              </h3>
              
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label htmlFor="heatmap-toggle">Show Heatmap</Label>
                  <Switch 
                    id="heatmap-toggle" 
                    checked={projectData.settings.showHeatmap}
                    onCheckedChange={(c) => updateSetting('showHeatmap', c)}
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label className="text-xs">Global Decay Rate</Label>
                    <span className="text-xs text-muted-foreground">{projectData.settings.globalDecay.toFixed(1)}</span>
                  </div>
                  <Slider 
                    value={[projectData.settings.globalDecay]} 
                    min={0.1} 
                    max={10} 
                    step={0.1}
                    onValueChange={([v]) => updateSetting('globalDecay', v)}
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label className="text-xs">Resolution (px)</Label>
                    <span className="text-xs text-muted-foreground">{projectData.settings.resolution}px</span>
                  </div>
                  <Slider 
                    value={[projectData.settings.resolution]} 
                    min={2} 
                    max={20} 
                    step={1}
                    onValueChange={([v]) => updateSetting('resolution', v)}
                  />
                  <p className="text-[10px] text-muted-foreground">Lower = higher quality, slower performance.</p>
                </div>
              </div>
            </div>

            <Separator />

            {/* Plan Upload */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Upload className="w-4 h-4" /> Floor Plan
              </h3>
              <div className="grid w-full max-w-sm items-center gap-1.5">
                <Label htmlFor="picture" className="text-xs">Background Image</Label>
                <Input 
                  id="picture" 
                  type="file" 
                  accept="image/*"
                  className="cursor-pointer text-xs" 
                  onChange={handleFileUpload}
                />
              </div>
            </div>
          </div>

          <div className="p-4 border-t border-border bg-secondary/50 space-y-2">
            <Button 
              className="w-full font-semibold gap-2" 
              onClick={handleSave}
              disabled={!isDirty || updateMutation.isPending}
            >
              {updateMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {isDirty ? 'Save Changes' : 'Saved'}
            </Button>
            
            <Button variant="outline" className="w-full gap-2 text-xs">
              <Download className="w-3 h-3" /> Export Heatmap
            </Button>
          </div>
        </aside>

        {/* Main Canvas Area */}
        <main className="flex-1 relative bg-slate-900">
          <SimulationCanvas 
            data={projectData} 
            mode={activeTool}
            onChange={(newData) => {
              setProjectData(newData);
              setIsDirty(true);
            }}
          />
        </main>
      </div>
    </div>
  );
}
