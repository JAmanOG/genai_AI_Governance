"use client"

import * as Icons from "lucide-react"
import { useAppData } from "@/lib/use-app-data"

interface KPIRibbonProps {
  selectedDistrict: string | null
}

export default function KPIRibbon({ selectedDistrict }: KPIRibbonProps) {
  const { data } = useAppData()
  const kpiData = data.kpiData

  return (
    <div className="grid grid-cols-4 gap-4">
      {Object.entries(kpiData).map(([key, item]) => {
        const Icon = (Icons as any)[item.iconName] ?? Icons.Info
        return (
          <div
            key={key}
            className="bg-card border border-border rounded-lg p-4 hover:border-primary/50 transition-colors group"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-foreground">{item.value}</p>
                <p className="text-xs text-muted-foreground mt-1">{item.label}</p>
              </div>
              <div className={`${item.color} opacity-60 group-hover:opacity-100 transition-opacity`}>
                <Icon className="w-6 h-6" />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
