import { useState, useRef, useEffect, useCallback } from "react";
import { Stage, Layer, Image as KonvaImage, Circle, Line, Group } from "react-konva";
import useImage from "use-image";
import Konva from "konva";
import { Fan, Obstacle, ProjectData } from "@shared/schema";
import { calculateIntensityAtPoint, getHeatmapColor } from "@/lib/simulation-utils";

interface SimulationCanvasProps {
  data: ProjectData;
  mode: 'select' | 'fan' | 'obstacle';
  onChange: (data: ProjectData) => void;
}

export function SimulationCanvas({ data, mode, onChange }: SimulationCanvasProps) {
  // Canvas references
  const stageRef = useRef<Konva.Stage>(null);
  const heatmapLayerRef = useRef<Konva.Layer>(null);
  
  // State
  const [backgroundImage] = useImage(data.backgroundImage || "");
  const [tempObstaclePoints, setTempObstaclePoints] = useState<{x: number, y: number}[]>([]);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  // Heatmap generation logic
  const generateHeatmap = useCallback(() => {
    if (!heatmapLayerRef.current) return;
    
    // Only generate if showing heatmap is enabled
    if (!data.settings.showHeatmap) {
      heatmapLayerRef.current.destroyChildren();
      return;
    }

    const stage = stageRef.current;
    if (!stage) return;
    
    // Resolution optimization (skip pixels)
    const resolution = Math.max(2, data.settings.resolution); // 5px blocks default
    const width = stage.width();
    const height = stage.height();
    
    // Use raw canvas API for performance
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(width / resolution);
    canvas.height = Math.ceil(height / resolution);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Simulation loop
    for (let y = 0; y < canvas.height; y++) {
      for (let x = 0; x < canvas.width; x++) {
        // Map back to world coordinates
        const worldX = x * resolution;
        const worldY = y * resolution;
        
        const intensity = calculateIntensityAtPoint(
          { x: worldX, y: worldY },
          data.fans,
          data.obstacles,
          data.settings.globalDecay
        );
        
        ctx.fillStyle = getHeatmapColor(intensity);
        ctx.fillRect(x, y, 1, 1);
      }
    }

    // Draw the result onto Konva layer
    heatmapLayerRef.current.destroyChildren();
    const konvaImage = new Konva.Image({
      image: canvas,
      x: 0,
      y: 0,
      width: width,
      height: height,
      opacity: 0.7,
      listening: false // Don't catch clicks
    });
    
    heatmapLayerRef.current.add(konvaImage);
    heatmapLayerRef.current.batchDraw();

  }, [data.fans, data.obstacles, data.settings, backgroundImage]); // Re-run when scene changes

  // Trigger simulation when data changes
  useEffect(() => {
    // Debounce slightly to prevent freezing on dragging
    const timer = setTimeout(generateHeatmap, 50);
    return () => clearTimeout(timer);
  }, [generateHeatmap]);


  // --- INTERACTION HANDLERS ---

  const handleStageClick = (e: Konva.KonvaEventObject<MouseEvent>) => {
    // Only handle clicks on empty space (stage or background)
    const clickedOnEmpty = e.target === e.target.getStage();
    const pos = e.target.getStage()?.getRelativePointerPosition();
    if (!pos) return;

    if (mode === 'fan') {
      const newFan: Fan = {
        id: crypto.randomUUID(),
        x: pos.x,
        y: pos.y,
        radius: 30,
        intensity: 1.0,
        decay: 2.0
      };
      onChange({ ...data, fans: [...data.fans, newFan] });
    } else if (mode === 'obstacle') {
      setTempObstaclePoints([...tempObstaclePoints, pos]);
    }
  };

  const handleObstacleComplete = () => {
    if (tempObstaclePoints.length < 3) {
      setTempObstaclePoints([]); // Cancel if too few points
      return;
    }
    const newObstacle: Obstacle = {
      id: crypto.randomUUID(),
      points: tempObstaclePoints
    };
    onChange({ ...data, obstacles: [...data.obstacles, newObstacle] });
    setTempObstaclePoints([]);
  };

  const handleFanDrag = (id: string, newPos: { x: number; y: number }) => {
    const updatedFans = data.fans.map(f => f.id === id ? { ...f, ...newPos } : f);
    onChange({ ...data, fans: updatedFans });
  };

  // Double click to close polygon
  const handleStageDblClick = () => {
    if (mode === 'obstacle') {
      handleObstacleComplete();
    }
  };


  return (
    <div className="w-full h-full bg-slate-950 overflow-hidden relative canvas-container">
      <Stage
        ref={stageRef}
        width={window.innerWidth - 300} // Subtract sidebar width roughly
        height={window.innerHeight - 64} // Subtract navbar
        onMouseDown={handleStageClick}
        onDblClick={handleStageDblClick}
        draggable={mode === 'select'}
      >
        <Layer>
          {/* Background Plan */}
          {backgroundImage && (
            <KonvaImage
              image={backgroundImage}
              opacity={0.5}
            />
          )}
        </Layer>

        {/* Heatmap Layer */}
        <Layer ref={heatmapLayerRef} />

        {/* Objects Layer */}
        <Layer>
          {/* Fans */}
          {data.fans.map((fan) => (
            <Group
              key={fan.id}
              x={fan.x}
              y={fan.y}
              draggable={mode === 'select'}
              onDragEnd={(e) => handleFanDrag(fan.id, { x: e.target.x(), y: e.target.y() })}
            >
              {/* Visual representation of Fan */}
              <Circle
                radius={fan.radius}
                fill="rgba(6, 182, 212, 0.2)"
                stroke="#06b6d4"
                strokeWidth={2}
              />
              {/* Center point */}
              <Circle radius={4} fill="#06b6d4" />
              {/* Label */}
              <Konva.Text
                text="FAN"
                fontSize={10}
                fill="#06b6d4"
                y={-fan.radius - 15}
                x={-10}
              />
            </Group>
          ))}

          {/* Obstacles */}
          {data.obstacles.map((obs) => (
            <Line
              key={obs.id}
              points={obs.points.flatMap(p => [p.x, p.y])}
              closed
              fill="rgba(255, 255, 255, 0.1)"
              stroke="#f97316" // Orange
              strokeWidth={2}
              draggable={mode === 'select'}
            />
          ))}

          {/* Drawing Obstacle (Preview) */}
          {tempObstaclePoints.length > 0 && (
            <Line
              points={tempObstaclePoints.flatMap(p => [p.x, p.y])}
              stroke="#f97316"
              strokeWidth={2}
              dash={[10, 5]}
            />
          )}
        </Layer>
      </Stage>

      {/* Floating hints */}
      <div className="absolute bottom-4 left-4 bg-background/80 backdrop-blur px-4 py-2 rounded-lg border border-border text-xs text-muted-foreground pointer-events-none">
        {mode === 'select' && "Drag canvas to pan • Drag objects to move"}
        {mode === 'fan' && "Click anywhere to place a fan"}
        {mode === 'obstacle' && "Click to place points • Double-click to close shape"}
      </div>
    </div>
  );
}
