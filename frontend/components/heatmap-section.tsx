"use client"

import { AlertTriangle, AlertCircle, CheckCircle, Info } from "lucide-react"
import { useAppData } from "@/lib/use-app-data"

const getRiskColor = (level: string) => {
  switch (level) {
    case "critical":
      return "bg-red-600 hover:bg-red-700"
    case "high":
      return "bg-orange-600 hover:bg-orange-700"
    case "medium":
      return "bg-yellow-600 hover:bg-yellow-700"
    case "low":
      return "bg-green-600 hover:bg-green-700"
    default:
      return "bg-slate-600"
  }
}

const getRiskIcon = (level: string) => {
  switch (level) {
    case "critical":
      return AlertCircle
    case "high":
      return AlertTriangle
    case "medium":
      return Info
    case "low":
      return CheckCircle
    default:
      return Info
  }
}

interface HeatmapSectionProps {
  selectedDistrict: string | null
  onDistrictClick: (district: string) => void
}

export default function HeatmapSection({ selectedDistrict, onDistrictClick }: HeatmapSectionProps) {
  const { data } = useAppData()
  const districtRisks = data.districtRisks

  return (
    <div className="bg-card border border-border rounded-lg p-6">
      <h2 className="text-lg font-bold text-foreground mb-4">Maharashtra Risk Heatmap</h2>

      <div className="bg-input rounded-lg p-8 mb-4 min-h-64 flex items-center justify-center border border-border/50">
        <p className="text-muted-foreground text-center">
          Interactive Map Visualization
          <br />
          <span className="text-xs">(District risk heatmap would render here )</span>
        </p>
      </div>

      <div className="space-y-3">
        {Object.entries(districtRisks).map(([district, { risk, level }]) => {
          const Icon = getRiskIcon(level)
          return (
            <button
              key={district}
              onClick={() => onDistrictClick(district)}
              className={`w-full p-3 rounded-lg transition-all border ${
                selectedDistrict === district
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-primary/50 bg-input/30"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Icon className="w-5 h-5 text-muted-foreground" />
                  <div className="text-left">
                    <p className="font-semibold text-foreground">{district}</p>
                    <p className="text-xs text-muted-foreground">Risk Level: {level.toUpperCase()}</p>
                  </div>
                </div>
                <div className={`px-3 py-1 rounded-full text-sm font-bold text-white ${getRiskColor(level)}`}>
                  {risk}%
                </div>
              </div>
            </button>
          )
        })}
      </div>

      <div className="mt-4 p-3 bg-input/30 rounded-lg border border-border/50">
        <p className="text-xs text-muted-foreground text-center">
          Legend: Critical {">70%"} • High {" 50-70%"} • Medium {" 30-50%"} • Low {"<30%"}
        </p>
      </div>
    </div>
  )
}
