import { Link } from "wouter";
import { Wind, FileText, Settings, User } from "lucide-react";

export function Navbar() {
  return (
    <nav className="h-16 border-b border-border bg-background/50 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-50">
      <div className="flex items-center gap-2">
        <div className="bg-primary/20 p-2 rounded-lg">
          <Wind className="w-6 h-6 text-primary" />
        </div>
        <Link href="/" className="font-display font-bold text-xl tracking-tight hover:opacity-80 transition-opacity">
          AirFlow<span className="text-primary">Sim</span>
        </Link>
      </div>

      <div className="flex items-center gap-6">
        <Link href="/" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
          Dashboard
        </Link>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center border border-border">
            <User className="w-4 h-4 text-muted-foreground" />
          </div>
        </div>
      </div>
    </nav>
  );
}
