"use client"

import { AlertCircle, AlertTriangle, Info, Clock } from "lucide-react"
import { useAppData } from "@/lib/use-app-data"

const getLevelColor = (level: string) => {
  switch (level) {
    case "critical":
      return "border-l-red-600 bg-red-600/5"
    case "high":
      return "border-l-orange-600 bg-orange-600/5"
    case "medium":
      return "border-l-yellow-600 bg-yellow-600/5"
    default:
      return "border-l-blue-600 bg-blue-600/5"
  }
}

const getLevelIcon = (level: string) => {
  switch (level) {
    case "critical":
      return AlertCircle
    case "high":
      return AlertTriangle
    case "medium":
      return Info
    default:
      return Info
  }
}

interface AlertFeedProps {
  selectedDistrict: string | null
}

export default function AlertFeed({ selectedDistrict }: AlertFeedProps) {
  const { data } = useAppData()
  const alerts = data.alerts
  const filtered = selectedDistrict ? alerts.filter((a) => a.district.includes(selectedDistrict)) : alerts

  return (
    <div className="bg-card border border-border rounded-lg p-6 h-full">
      <h2 className="text-lg font-bold text-foreground mb-4">Live Alert Stream</h2>

      <div className="space-y-3 max-h-[calc(100vh-300px)] overflow-y-auto">
        {filtered.map((alert) => {
          const Icon = getLevelIcon(alert.level)
          return (
            <div key={alert.id} className={`border-l-4 rounded p-3 transition-colors ${getLevelColor(alert.level)}`}>
              <div className="flex justify-between items-start mb-2 gap-2">
                <div className="flex items-start gap-2 flex-1">
                  <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                  <p className="font-semibold text-foreground text-sm">{alert.title}</p>
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                  <Clock className="w-3 h-3" />
                  {alert.time}
                </div>
              </div>

              <p className="text-xs text-muted-foreground mb-1 ml-6">{alert.district}</p>
              <p className="text-xs text-foreground mb-2 ml-6">{alert.description}</p>

              {alert.trigger && (
                <div className="bg-background/50 rounded p-2 mb-2 border border-border/50 ml-6">
                  <p className="text-xs text-muted-foreground">
                    <span className="font-semibold">Trigger:</span> {alert.trigger}
                  </p>
                </div>
              )}

              <div className="flex flex-wrap gap-1 ml-6">
                {alert.actions.map((action, idx) => (
                  <span key={idx} className="text-xs bg-primary/20 text-primary px-2 py-1 rounded">
                    {action}
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
