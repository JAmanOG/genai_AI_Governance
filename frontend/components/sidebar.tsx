"use client"

import { useAppData } from "@/lib/use-app-data"

const timeRanges = [
  { id: "live", label: "Live", icon: "●" },
  { id: "7days", label: "Last 7 Days", icon: "○" },
  { id: "30days", label: "Last 30 Days", icon: "○" },
  { id: "custom", label: "Custom Range", icon: "○" },
]

interface SidebarProps {
  selectedDistrict: string | null
  onDistrictSelect: (district: string | null) => void
  timeRange: string
  onTimeRangeChange: (range: string) => void
}

export default function Sidebar({ selectedDistrict, onDistrictSelect, timeRange, onTimeRangeChange }: SidebarProps) {
  const { data } = useAppData()
  const districts = [...Object.keys(data.districtRisks), "All Districts"]

  return (
    <aside className="w-56 bg-sidebar border-r border-sidebar-border h-full overflow-y-auto">
      <div className="p-4 space-y-6">
        {/* Districts */}
        <div>
          <h3 className="text-xs font-bold text-sidebar-foreground mb-3 opacity-70">DISTRICTS</h3>
          <div className="space-y-2">
            {districts.map((district) => (
              <button
                key={district}
                onClick={() => onDistrictSelect(district === selectedDistrict || district === "All Districts" ? null : district)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                  selectedDistrict === district
                    ? "bg-sidebar-primary text-sidebar-primary-foreground font-semibold"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/30"
                }`}
              >
                <span className="mr-2">{selectedDistrict === district ? "█" : "□"}</span>
                {district}
              </button>
            ))}
          </div>
        </div>

        {/* Timeline */}
        <div>
          <h3 className="text-xs font-bold text-sidebar-foreground mb-3 opacity-70">TIMELINE</h3>
          <div className="space-y-2">
            {timeRanges.map((range) => (
              <button
                key={range.id}
                onClick={() => onTimeRangeChange(range.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition-colors flex items-center gap-2 ${
                  timeRange === range.id
                    ? "text-sidebar-primary-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/30"
                }`}
              >
                <span className={timeRange === range.id ? "●" : "○"}></span>
                {range.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </aside>
  )
}
