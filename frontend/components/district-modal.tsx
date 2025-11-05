"use client"

import { X, AlertCircle, AlertTriangle } from "lucide-react"
import { useAppData } from "@/lib/use-app-data"
import { getDistrictDetails, buildDepartments } from "@/lib/derived"
import { useEffect, useState } from "react"

interface DistrictModalProps {
  district: string
  onClose: () => void
}

type DistrictAI = { actions: string[]; confidence: number; explanation: string }

export default function DistrictModal({ district, onClose }: DistrictModalProps) {
  const { data } = useAppData()
  const details = getDistrictDetails(data, district)

  const [ai, setAi] = useState<DistrictAI | null>(null)
  const [aiLoading, setAiLoading] = useState<boolean>(false)
  const [aiError, setAiError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setAi(null)
      setAiError(null)
      setAiLoading(true)

      // Relaxed data sufficiency check: proceed if ANY real signal exists
      const departments = buildDepartments(data, district)
      const hasOverview = details.overview.risk !== undefined // level may be derived later
      const hasTriggers = details.triggers.length > 0
      const hasInsights = details.insights.length > 0
      const hasDeptSignals = departments.some(
        (d) => (d.factors && d.factors.length > 0) || d.metrics.some((m) => m.value && m.value !== "—")
      )

      if (!hasOverview && !hasTriggers && !hasInsights && !hasDeptSignals) {
        if (!cancelled) setAiError("No data available for this district")
        if (!cancelled) setAiLoading(false)
        return
      }

      try {
        const res = await fetch("/api/ai/gemini", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: "district",
            district,
            context: {
              overview: details.overview,
              triggers: details.triggers,
              insights: details.insights,
              departments,
              allAlerts: data.alerts.filter(a => a.district.includes(district)),
            },
          }),
        })
        if (!res.ok) throw new Error(`AI HTTP ${res.status}`)
        const json = await res.json()
        // Strict shape already validated on server; minimal guard here
        if (!Array.isArray(json?.actions) || typeof json?.confidence !== "number" || typeof json?.explanation !== "string") {
          throw new Error("AI schema invalid")
        }
        if (!cancelled) setAi({ actions: json.actions, confidence: json.confidence, explanation: json.explanation })
      } catch (e: any) {
        if (!cancelled) setAiError(e?.message || "AI failed")
      } finally {
        if (!cancelled) setAiLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [district])

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-card border-b border-border p-6 flex justify-between items-center">
          <h2 className="text-2xl font-bold text-foreground">{district} District - Detailed View</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 hover:bg-input rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Overview */}
          <div>
            <p className="text-sm text-muted-foreground mb-2">
              Overall Risk Score:{" "}
              <span className={`text-lg font-bold ${
                details.overview.level === "critical"
                  ? "text-red-500"
                  : details.overview.level === "high"
                  ? "text-orange-500"
                  : details.overview.level === "medium"
                  ? "text-yellow-500"
                  : "text-green-500"
              }`}
              >
                {details.overview.risk ?? "—"}%
              </span>
            </p>
            <p className="text-sm text-foreground">Level: {details.overview.level?.toUpperCase() ?? "—"}</p>
          </div>

          {/* Recommended Actions (AI) */}
          <div className="bg-input/30 rounded-lg p-4 border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle className="w-5 h-5 text-emerald-500" />
              <h3 className="font-bold text-foreground">Recommended Actions</h3>
            </div>
            {aiLoading && <p className="text-xs text-muted-foreground">Generating...</p>}
            {aiError && (
              <div className="text-xs text-red-500 flex items-center justify-between">
                <span>{aiError}</span>
                <button
                  className="underline text-foreground/80 hover:text-foreground"
                  onClick={() => {
                    // retry with the same data sufficiency check
                    setAiLoading(true)
                    setAiError(null)

                    const departments = buildDepartments(data, district)
                    const hasOverview = details.overview.risk !== undefined
                    const hasTriggers = details.triggers.length > 0
                    const hasInsights = details.insights.length > 0
                    const hasDeptSignals = departments.some(
                      (d) => (d.factors && d.factors.length > 0) || d.metrics.some((m) => m.value && m.value !== "—")
                    )

                    if (!hasOverview && !hasTriggers && !hasInsights && !hasDeptSignals) {
                      setAiLoading(false)
                      setAiError("No data available for this district")
                      return
                    }

                    fetch("/api/ai/gemini", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ type: "district", district, context: { overview: details.overview, triggers: details.triggers, insights: details.insights, departments, allAlerts: data.alerts.filter(a => a.district.includes(district)) } }),
                    })
                      .then(async (r) => {
                        if (!r.ok) throw new Error(`AI HTTP ${r.status}`)
                        const j = await r.json()
                        if (!Array.isArray(j?.actions) || typeof j?.confidence !== "number" || typeof j?.explanation !== "string") {
                          throw new Error("AI schema invalid")
                        }
                        setAi({ actions: j.actions, confidence: j.confidence, explanation: j.explanation })
                      })
                      .catch((e) => setAiError(e?.message || "AI failed"))
                      .finally(() => setAiLoading(false))
                  }}
                >Retry</button>
              </div>
            )}
            {!aiLoading && !aiError && ai && (
              <ul className="space-y-2 text-sm list-disc list-inside text-foreground">
                {ai.actions.map((a, idx) => (
                  <li key={idx}>{a}</li>
                ))}
              </ul>
            )}
          </div>

          {/* AI Confidence & Explanation */}
          <div className="bg-input/30 rounded-lg p-4 border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle className="w-5 h-5 text-blue-500" />
              <h3 className="font-bold text-foreground">AI Confidence & Explanation</h3>
            </div>
            {ai ? (
              <div className="text-sm text-foreground space-y-2">
                <p>Confidence: {Math.round(ai.confidence * 100)}%</p>
                <p className="text-muted-foreground whitespace-pre-wrap">{ai.explanation}</p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Awaiting AI analysis...</p>
            )}
          </div>

          {/* Predictive Insights (from health alerts) */}
          <div className="bg-input/30 rounded-lg p-4 border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle className="w-5 h-5 text-red-500" />
              <h3 className="font-bold text-foreground">Predictive Insights</h3>
            </div>
            {details.insights.length === 0 ? (
              <p className="text-xs text-muted-foreground">No recent insights.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {details.insights.map((i, idx) => (
                  <li key={idx} className="text-foreground">
                    <span className="font-semibold">{i.title}</span>
                    {i.description ? <span className="ml-1 text-muted-foreground">— {i.description}</span> : null}
                    {i.time ? <span className="ml-2 text-xs text-muted-foreground">({i.time})</span> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Triggering Factors */}
          <div className="bg-input/30 rounded-lg p-4 border border-border/50">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-orange-500" />
              <h3 className="font-bold text-foreground">Triggering Factors (PS-Police Station)</h3>
            </div>
            {details.triggers.length === 0 ? (
              <p className="text-xs text-muted-foreground">No key triggers identified.</p>
            ) : (
              <ul className="space-y-2 text-sm text-foreground list-disc list-inside">
                {details.triggers.map((t, idx) => (
                  <li key={idx}>{t}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
