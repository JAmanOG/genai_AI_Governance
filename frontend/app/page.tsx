"use client"

import { useState } from "react"
import Header from "@/components/header"
import Sidebar from "@/components/sidebar"
import KPIRibbon from "@/components/kpi-ribbon"
import HeatmapSection from "@/components/heatmap-section"
import AlertFeed from "@/components/alert-feed"
import DepartmentCards from "@/components/department-cards"
import DistrictModal from "@/components/district-modal"

export default function DashboardPage() {
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null)
  const [timeRange, setTimeRange] = useState("7days")

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <div className="flex h-[calc(100vh-64px)]">
        <Sidebar
          selectedDistrict={selectedDistrict}
          onDistrictSelect={setSelectedDistrict}
          timeRange={timeRange}
          onTimeRangeChange={setTimeRange}
        />

        <main className="flex-1 overflow-auto">
          <div className="p-6 space-y-6">
            <KPIRibbon selectedDistrict={selectedDistrict} />

            <div className="grid grid-cols-3 gap-6">
              <div className="col-span-2">
                <HeatmapSection selectedDistrict={selectedDistrict} onDistrictClick={setSelectedDistrict} />
              </div>
              <div>
                <AlertFeed selectedDistrict={selectedDistrict} />
              </div>
            </div>

            <DepartmentCards selectedDistrict={selectedDistrict} />

            {selectedDistrict && (
              <DistrictModal district={selectedDistrict} onClose={() => setSelectedDistrict(null)} />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
