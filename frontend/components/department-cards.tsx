"use client"

import * as Icons from "lucide-react"
import { useAppData } from "@/lib/use-app-data"
import { buildDepartments } from "@/lib/derived"
import { useEffect, useMemo, useState } from "react"

interface DepartmentCardsProps {
  selectedDistrict: string | null
}

type AIFactor = { name: string; status: string }

export default function DepartmentCards({ selectedDistrict }: DepartmentCardsProps) {
  const { data } = useAppData()
  const baseDepartments = buildDepartments(data, selectedDistrict)

  const [aiFactors, setAIFactors] = useState<Record<string, AIFactor[]>>({})
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)

  const departments = useMemo(() => {
    return baseDepartments.map((d) => ({
      ...d,
      factors: aiFactors[d.id] && aiFactors[d.id]!.length ? aiFactors[d.id]! : d.factors,
    }))
  }, [baseDepartments, aiFactors])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setAiError(null)
      if (!selectedDistrict) {
        setAIFactors({})
        return
      }
      setAiLoading(true)
      try {
        const res = await fetch("/api/ai/gemini", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: "department",
            district: selectedDistrict,
            departments: baseDepartments.map((d) => ({ id: d.id, title: d.title })),
            context: {
              // lightweight context to steer Gemini
              metrics: baseDepartments.map((d) => ({ id: d.id, title: d.title, metrics: d.metrics })),
              defaultFactors: baseDepartments.map((d) => ({ id: d.id, factors: d.factors })),
            },
          }),
        })
        if (!res.ok) throw new Error(`AI HTTP ${res.status}`)
        const json = await res.json()
        const mapArr: Array<{ id: string; factors: AIFactor[] }> = json?.factorsByDepartment || []
        const next: Record<string, AIFactor[]> = {}
        for (const item of mapArr) {
          const id = String(item?.id || "")
          const fs = Array.isArray(item?.factors) ? item.factors : []
          if (id && fs.length) next[id] = fs.slice(0, 3)
        }
        if (!cancelled) setAIFactors(next)
      } catch (e: any) {
        if (!cancelled) setAiError(e?.message || "AI failed")
      } finally {
        if (!cancelled) setAiLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [selectedDistrict])

  return (
    <div className="grid grid-cols-2 gap-6">
      {departments.map((dept) => {
        const Icon = (Icons as any)[dept.iconName] ?? Icons.Info
        return (
          <div
            key={dept.id}
            className="bg-card border border-border rounded-lg p-6 hover:border-primary/50 transition-colors"
          >
            <div className="flex items-center gap-3 mb-4">
              <Icon className={`w-6 h-6 ${dept.color}`} />
              <h3 className="text-lg font-bold text-foreground">{dept.title}</h3>
            </div>

            <div className="grid grid-cols-4 gap-2 mb-4">
              {dept.metrics.map((metric, idx) => (
                <div key={idx} className="bg-input/30 rounded p-2 border border-border/30">
                  <p className="text-xs text-muted-foreground mb-1">{metric.label}</p>
                  <p className="font-bold text-foreground text-sm">{metric.value}</p>
                  {metric.status && <p className="text-xs text-primary mt-1">{metric.status}</p>}
                </div>
              ))}
            </div>

            <div className="bg-input/20 rounded p-3 border border-border/30">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-muted-foreground mb-2">Top Risk Factors:</p>
                {aiLoading && selectedDistrict && <p className="text-[10px] text-muted-foreground">AI updating…</p>}
              </div>
              {aiError && (
                <p className="text-[10px] text-red-500 mb-1">{aiError}</p>
              )}
              <div className="space-y-1">
                {dept.factors.map((factor, idx) => (
                  <p key={idx} className="text-xs text-foreground">
                    <span className="mr-2">{factor.status}</span>
                    {factor.name}
                  </p>
                ))}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
