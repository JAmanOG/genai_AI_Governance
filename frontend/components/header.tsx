"use client"

import { AlertCircle, Database } from "lucide-react"
import { ThemeToggle } from "./theme-toggle"
import { Button } from "@/components/ui/button"
import { useDataMode } from "@/lib/data-mode"

export default function Header() {
  const { useMock, setUseMock } = useDataMode()
  return (
    <header className="h-16 bg-card border-b border-border px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
          <span className="text-primary-foreground font-bold text-sm">MH</span>
        </div>
        <div>
          <h1 className="text-lg font-bold text-foreground">Maharashtra AI Governance</h1>
          <p className="text-xs text-muted-foreground">Intelligence Platform</p>
        </div>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
          <span className="text-muted-foreground">Real-time Active</span>
        </div>
        <span className="text-muted-foreground">Last Updated: 2 min ago</span>
        <div className="flex items-center gap-2 bg-destructive/10 px-3 py-1.5 rounded-lg border border-destructive/20">
          <AlertCircle className="w-4 h-4 text-destructive" />
          <span className="font-semibold text-destructive">3 Critical</span>
        </div>
        
        <Button
          variant={useMock ? "secondary" : "outline"}
          size="sm"
          onClick={() => setUseMock(!useMock)}
          title={useMock ? "Using demo data (click to switch to live)" : "Using live data (click to switch to demo)"}
          aria-pressed={useMock}
        >
          <Database className="w-4 h-4" />
          {useMock ? "Demo Data: On" : "Demo Data: Off"}
        </Button>

        <ThemeToggle />
      </div>
    </header>
  )
}