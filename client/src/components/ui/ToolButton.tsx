import React from "react";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface ToolButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  icon: LucideIcon;
  label: string;
}

export function ToolButton({ 
  active, 
  icon: Icon, 
  label, 
  className, 
  ...props 
}: ToolButtonProps) {
  return (
    <button
      className={cn(
        "flex flex-col items-center justify-center gap-1 p-3 rounded-xl transition-all duration-200 border border-transparent w-full",
        active 
          ? "bg-primary/10 border-primary/20 text-primary shadow-lg shadow-primary/10" 
          : "text-muted-foreground hover:bg-secondary hover:text-foreground hover:border-border",
        className
      )}
      {...props}
    >
      <Icon className={cn("w-6 h-6", active && "animate-pulse")} />
      <span className="text-[10px] font-medium uppercase tracking-wider">{label}</span>
    </button>
  );
}
