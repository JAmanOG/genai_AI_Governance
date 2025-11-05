"use client"

import { useEffect, useMemo, useState } from "react"
import { appData as demoAppData, type AppData, type KPIData, type DistrictRisks, type AlertItem } from "./app-data"
import { useDataMode } from "@/lib/data-mode"

const ENDPOINT = "/api/enriched_dashboard"

function levelFromRisk(risk: number): "critical" | "high" | "medium" | "low" {
  if (risk >= 70) return "critical"
  if (risk >= 50) return "high"
  if (risk >= 30) return "medium"
  return "low"
}

function toTimeAgo(iso: string | undefined): string {
  if (!iso) return "just now"
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const now = Date.now()
  const diffMs = Math.max(0, now - then)
  const sec = Math.floor(diffMs / 1000)
  const min = Math.floor(sec / 60)
  const hr = Math.floor(min / 60)
  const day = Math.floor(hr / 24)
  if (day > 0) return `${day} day${day > 1 ? "s" : ""} ago`
  if (hr > 0) return `${hr} hour${hr > 1 ? "s" : ""} ago`
  if (min > 0) return `${min} minute${min > 1 ? "s" : ""} ago`
  return `${sec} second${sec !== 1 ? "s" : ""} ago`
}

function mapDistrictRisks(input: any): DistrictRisks | null {
  if (!input || typeof input !== "object") return null
  const out: DistrictRisks = {}
  for (const [name, val] of Object.entries(input as Record<string, any>)) {
    const risk = typeof (val as any)?.risk === "number" ? (val as any).risk : Number((val as any)?.risk) || 0
    const level = (val as any)?.level || levelFromRisk(risk)
    out[name] = { risk, level }
  }
  return out
}

function mapAlerts(input: any): AlertItem[] | null {
  if (!Array.isArray(input)) return null
  return input.map((a: any, idx: number): AlertItem => ({
    id: (a?.id ?? idx) as string | number,
    district: String(a?.district ?? "Unknown"),
    level: (a?.level as any) ?? levelFromRisk(Number(a?.raw_score ?? 0) * 100),
    title: String(a?.title ?? "Alert"),
    description: String(a?.description ?? ""),
    trigger: String(a?.trigger ?? ""),
    actions: Array.isArray(a?.actions) ? a.actions.map(String) : [],
    time: toTimeAgo(String(a?.time)),
  }))
}

function isValidKPIData(obj: any): obj is KPIData {
  return obj && typeof obj === "object" && obj.critical && obj.highRisk && obj.population && obj.budget
}

function pickHealthAlerts(json: any): any[] | null {
  const arr = json?.pipelines?.health?.data
  return Array.isArray(arr) ? arr : null
}

function pickInfraDistricts(json: any): any | null {
  const obj = json?.pipelines?.infrastructure?.data
  return obj && typeof obj === "object" ? obj : null
}

export function useAppData() {
  const { useMock } = useDataMode()
  const [data, setData] = useState<AppData | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadLive() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(ENDPOINT, { cache: "no-store" })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()

        const kpis: KPIData = isValidKPIData(json?.kpiData) ? json.kpiData : demoAppData.kpiData
        const drFromRoot = mapDistrictRisks(json?.districtRisks)
        const drFromInfra = mapDistrictRisks(pickInfraDistricts(json))
        const districtRisks: DistrictRisks = drFromRoot ?? drFromInfra ?? demoAppData.districtRisks
        const alertsFromRoot = mapAlerts(json?.alerts)
        const alertsFromHealth = mapAlerts(pickHealthAlerts(json))
        const alerts: AlertItem[] = alertsFromRoot ?? alertsFromHealth ?? demoAppData.alerts
        const departments = demoAppData.departments // TODO: map when API provides compatible schema

        const mapped: AppData = { kpiData: kpis, districtRisks, alerts, departments, pipelines: json?.pipelines }
        if (!cancelled) setData(mapped)
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message ?? "Failed to load data")
          setData(demoAppData)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    if (useMock) {
      setData(demoAppData)
      setError(null)
      setLoading(false)
      return () => { cancelled = true }
    } else {
      loadLive()
      return () => { cancelled = true }
    }
  }, [useMock])

  return useMemo(
    () => ({ data: data ?? demoAppData, loading, error }),
    [data, loading, error]
  )
}
