import { type AppData, type Department, type DepartmentMetric, type DepartmentFactor } from "./app-data"

function cloneDepartments(source: Department[] | undefined): Department[] {
  if (!Array.isArray(source)) return []
  return source.map((dept) => ({
    ...dept,
    metrics: dept.metrics.map((m) => ({ ...m })),
    factors: dept.factors.map((f) => ({ ...f })),
  }))
}

function hasPipelineSignals(data: AppData): boolean {
  const pipelines = data.pipelines
  if (!pipelines) return false
  const health = pipelines.health?.data
  const infra = pipelines.infrastructure?.data
  const safetyScores = pipelines.publicSafety?.data?.scores
  const safetyDash = pipelines.publicSafety?.data?.dashboard
  const csf = pipelines.citizenServicesFeedback?.data
  return (
    (Array.isArray(health) && health.length > 0) ||
    (infra && Object.keys(infra).length > 0) ||
    (Array.isArray(safetyScores) && safetyScores.length > 0) ||
    (safetyDash && Object.keys(safetyDash).length > 0) ||
    (Array.isArray(csf?.forecasts) && csf.forecasts.length > 0)
  )
}

function fmtPct(n: number | undefined): string {
  if (n === undefined || Number.isNaN(n)) return "—"
  return `${Math.round(n)}%`
}

function fmtCr(n: number | undefined): string {
  if (n === undefined || Number.isNaN(n)) return "—"
  return `₹${Number(n).toFixed(0)} Cr`
}

function safeAvg(arr: Array<number | null | undefined>): number | undefined {
  const nums = arr.map((x) => (x == null ? NaN : Number(x))).filter((x) => Number.isFinite(x)) as number[]
  if (!nums.length) return undefined
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

function sum(arr: Array<number | null | undefined>): number | undefined {
  const nums = arr.map((x) => (x == null ? NaN : Number(x))).filter((x) => Number.isFinite(x)) as number[]
  if (!nums.length) return undefined
  return nums.reduce((a, b) => a + b, 0)
}

function getInfraForDistrict(data: AppData, district?: string) {
  const infra = data.pipelines?.infrastructure?.data
  if (!infra) return null
  if (district) return infra[district] ?? null
  return infra
}

function getHealthAlertsForDistrict(data: AppData, district?: string) {
  const arr: any[] = data.pipelines?.health?.data || []
  if (!district) return arr
  return arr.filter((a) => String(a?.district || "").includes(district))
}

function getSafetyScoresForDistrict(data: AppData, district?: string) {
  const arr: any[] = data.pipelines?.publicSafety?.data?.scores || []
  if (!district) return arr
  return arr.filter((x) => x?.district === district)
}

function getSafetyDashForDistrict(data: AppData, district?: string) {
  const dash = data.pipelines?.publicSafety?.data?.dashboard
  if (!dash) return null
  if (!district) return dash
  return dash[district] ?? null
}

function getCSFForecastsForDistrict(data: AppData, district?: string) {
  const arr: any[] = data.pipelines?.citizenServicesFeedback?.data?.forecasts || []
  if (!district) return arr
  return arr.filter((x) => x?.district === district)
}

export function buildDepartments(data: AppData, district: string | null): Department[] {
  if (!hasPipelineSignals(data)) {
    return cloneDepartments(data.departments)
  }

  const selected = district ?? undefined

  // Health metrics
  const health = getHealthAlertsForDistrict(data, selected)
  const outbreakRisk = safeAvg(health.map((h) => Number(h?.raw_score) * 100))
  const patientLoad = safeAvg(health.map((h) => Number(h?.input_features?.patient_inflow_mean)))
  const healthFactors: DepartmentFactor[] = []
  const topTrigger = health?.[0]?.trigger as string | undefined
  if (topTrigger) healthFactors.push({ name: topTrigger, status: "📌" })

  const healthMetrics: DepartmentMetric[] = [
    { label: "Outbreak Risk", value: fmtPct(outbreakRisk) },
    { label: "Patient Load", value: patientLoad ? `${Math.round(patientLoad)}/day` : "—" },
    { label: "Vaccine Coverage", value: "—" },
    { label: "Response Time", value: "—" },
  ]

  // Infrastructure metrics
  const infraNode = getInfraForDistrict(data, selected)
  const infraMany = !selected && infraNode && typeof infraNode === "object" ? Object.values(infraNode) : null
  const backlogCr = selected ? infraNode?.backlog_cr : safeAvg((infraMany as any[] | null)?.map((x) => x?.backlog_cr) || [])
  const avgImpact = selected ? infraNode?.avg_impact : safeAvg((infraMany as any[] | null)?.map((x) => x?.avg_impact) || [])
  const criticalRoads = selected ? infraNode?.critical_roads_count : safeAvg((infraMany as any[] | null)?.map((x) => x?.critical_roads_count) || [])

  const infraMetrics: DepartmentMetric[] = [
    { label: "Condition Score", value: avgImpact ? `${Number(avgImpact).toFixed(1)}/10` : "—" },
    { label: "Repair Backlog", value: fmtCr(backlogCr) },
    { label: "Critical Roads", value: criticalRoads !== undefined ? String(Math.round(criticalRoads as number)) : "—" },
    { label: "Budget", value: "—" },
  ]
  const infraFactors: DepartmentFactor[] = []
  const topRoad = selected ? infraNode?.top_factor : undefined
  if (topRoad) infraFactors.push({ name: String(topRoad), status: "🛣️" })

  // Public Safety metrics
  const safetyScores = getSafetyScoresForDistrict(data, selected)
  const crimeRisk = safeAvg(safetyScores.map((s) => s?.crime_risk_0_100))
  const responseEff = safeAvg(safetyScores.map((s) => s?.response_efficiency_pct))
  const resolveRate = safeAvg(safetyScores.map((s) => s?.resolution_rate_pct))
  const hotspots = (safetyScores || []).filter((s) => !!s?.is_hotspot).length
  const safetyDash = getSafetyDashForDistrict(data, selected)
  const psTop = selected ? safetyDash?.top_factor_line : undefined

  const safetyMetrics: DepartmentMetric[] = [
    { label: "Crime Risk", value: fmtPct(crimeRisk) },
    { label: "Response Eff.", value: fmtPct(responseEff) },
    { label: "Resolved", value: fmtPct(resolveRate) },
    { label: "Hotspots", value: String(hotspots || 0) },
  ]
  const safetyFactors: DepartmentFactor[] = []
  if (psTop) safetyFactors.push({ name: String(psTop), status: "🚓" })

  // Citizen Services & Feedback metrics
  const csf = getCSFForecastsForDistrict(data, selected)
  const volume7d = sum(csf.map((f) => f?.forecast_next_7d))
  const backlogEta = safeAvg(csf.map((f) => f?.backlog_eta_days))
  const satisfaction = safeAvg(csf.map((f) => f?.expected_satisfaction_next_7d))
  const pending = sum(csf.map((f) => f?.open_eod))

  const citizenMetrics: DepartmentMetric[] = [
    { label: "Request Volume (7d)", value: volume7d !== undefined ? String(Math.round(volume7d)) : "—" },
    { label: "Avg Resolution", value: backlogEta !== undefined ? `${Number(backlogEta).toFixed(1)} days` : "—" },
    { label: "Satisfaction", value: satisfaction !== undefined ? `${Number(satisfaction).toFixed(1)}/10` : "—" },
    { label: "Pending", value: pending !== undefined ? String(Math.round(pending)) : "—" },
  ]

  const citizenFactors: DepartmentFactor[] = []
  const topLongBacklog = (csf || [])
    .filter((f) => Number(f?.backlog_eta_days) >= 100)
    .slice(0, 2)
    .map((f) => ({ name: `${f.service_type} (ETA ${Number(f.backlog_eta_days)}d)`, status: "⏳" }))
  citizenFactors.push(...topLongBacklog)

  const departments: Department[] = [
    {
      id: "health",
      iconName: "Heart",
      title: "Health & Disease Control",
      color: "text-red-500",
      metrics: healthMetrics,
      factors: healthFactors,
    },
    {
      id: "infrastructure",
      iconName: "Building2",
      title: "Infrastructure & Roads",
      color: "text-orange-500",
      metrics: infraMetrics,
      factors: infraFactors,
    },
    {
      id: "safety",
      iconName: "Shield",
      title: "Public Safety & Crime",
      color: "text-blue-500",
      metrics: safetyMetrics,
      factors: safetyFactors,
    },
    {
      id: "citizen",
      iconName: "Users",
      title: "Citizen Services & Feedback",
      color: "text-green-500",
      metrics: citizenMetrics,
      factors: citizenFactors,
    },
  ]

  return departments
}

export function getDistrictDetails(data: AppData, district: string) {
  const risk = data.districtRisks[district]?.risk
  const level = data.districtRisks[district]?.level

  const infra = getInfraForDistrict(data, district)
  const psDash = getSafetyDashForDistrict(data, district)
  const csf = getCSFForecastsForDistrict(data, district)
  const healthAlerts = getHealthAlertsForDistrict(data, district)

  const triggers: string[] = []
  if (infra?.top_factor) triggers.push(String(infra.top_factor))
  if (psDash?.top_factor_line) triggers.push(String(psDash.top_factor_line))
  const csfBreach = csf.filter((f) => Number(f?.expected_sla_breach_rate) > 0)
  if (csfBreach.length) triggers.push(`${csfBreach.length} CSF SLA risks`)

  const insights = healthAlerts.slice(0, 3).map((a) => ({
    title: a?.title ?? "Alert",
    description: a?.description ?? "",
    time: a?.time ?? "",
    level: a?.level ?? "medium",
  }))

  if (!triggers.length && !insights.length && !hasPipelineSignals(data)) {
    const districtLc = district.toLowerCase()
    const fallbackAlerts = (data.alerts || []).filter((a) =>
      String(a?.district || "").toLowerCase().includes(districtLc)
    )
    const fallbackTriggers = fallbackAlerts
      .map((a) => a?.trigger)
      .filter((t): t is string => !!t)
    const fallbackInsights = fallbackAlerts.slice(0, 3).map((a) => ({
      title: a?.title ?? "Alert",
      description: a?.description ?? "",
      time: a?.time ?? "",
      level: a?.level ?? "medium",
    }))
    triggers.push(...fallbackTriggers)
    insights.push(...fallbackInsights)
  }

  return {
    overview: { risk, level },
    triggers,
    insights,
  }
}
