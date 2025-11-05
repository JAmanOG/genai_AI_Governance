import { NextResponse } from "next/server"
import fs from "fs"
import path from "path"

const CLOUD_FUNC_URL = process.env.NEXT_PUBLIC_CLOUD_FUNC_URL ||
  "https://us-central1-artful-affinity-476513-t7.cloudfunctions.net/get_dashboard_data"

function avg(nums: number[]): number | null {
  const arr = nums.filter((n) => Number.isFinite(n))
  if (!arr.length) return null
  return arr.reduce((a, b) => a + b, 0) / arr.length
}

function sum(nums: number[]): number | null {
  const arr = nums.filter((n) => Number.isFinite(n))
  if (!arr.length) return null
  return arr.reduce((a, b) => a + b, 0)
}

function buildKpis(json: any) {
  const base = json?.kpiData || {}
  const alerts: any[] = Array.isArray(json?.alerts) ? json.alerts : (json?.pipelines?.health?.data || [])
  const districts = json?.districtRisks || json?.pipelines?.infrastructure?.data || {}
  const totalDistricts = Object.keys(districts).length || 0
  const highCount = Object.values(districts).filter((d: any) => {
    const r = Number((d as any)?.risk)
    return r >= 50
  }).length
  const criticalCount = alerts.filter((a) => a?.level === "critical").length

  return {
    critical: {
      value: base.critical?.value ?? criticalCount,
      label: base.critical?.label ?? "CRITICAL ALERTS",
      iconName: base.critical?.iconName ?? "AlertCircle",
      color: base.critical?.color ?? "text-destructive",
    },
    highRisk: {
      value: base.highRisk?.value ?? `${highCount}/${totalDistricts || "—"}`,
      label: base.highRisk?.label ?? "HIGH RISK DISTRICTS",
      iconName: base.highRisk?.iconName ?? "TrendingUp",
      color: base.highRisk?.color ?? "text-orange-500",
    },
    population: base.population ?? { value: "—", label: "AFFECTED POPULATION", iconName: "Users", color: "text-blue-500" },
    budget: base.budget ?? { value: "—", label: "BUDGET IMPACT", iconName: "Wallet", color: "text-emerald-500" },
  }
}

function enrichPublicSafety(json: any) {
  const data = json?.pipelines?.publicSafety?.data
  if (!data) return
  const dash = data.dashboard || {}
  const scores: any[] = data.scores || []

  const group: Record<string, any[]> = {}
  for (const s of scores) {
    const d = s?.district
    if (!d) continue
    if (!group[d]) group[d] = []
    group[d].push(s)
  }

  for (const [district, arr] of Object.entries(group)) {
    const crimeRisk = avg(arr.map((x: any) => Number(x?.crime_risk_0_100)))
    const response = avg(arr.map((x: any) => Number(x?.response_efficiency_pct)))
    const resolve = avg(arr.map((x: any) => Number(x?.resolution_rate_pct)))
    const hotCount = arr.filter((x: any) => !!x?.is_hotspot).length

    dash[district] = dash[district] || {}
    dash[district].metrics = dash[district].metrics || [crimeRisk ?? 0, response ?? 0, resolve ?? 0]
    dash[district].hotspots = dash[district].hotspots ?? hotCount
    dash[district].top_factor_line = dash[district].top_factor_line || `PS-${district.slice(0, 3).toUpperCase()} (Risk: ${Math.round((crimeRisk ?? 0))}%)`
    dash[district].alert = dash[district].alert || {
      title: "Public Safety",
      description: `Avg risk ${Math.round(crimeRisk ?? 0)}%, hotspots ${hotCount}`,
    }
  }

  json.pipelines.publicSafety.data.dashboard = dash
}

function enrichCSF(json: any) {
  const data = json?.pipelines?.citizenServicesFeedback?.data
  if (!data) return
  const forecasts: any[] = Array.isArray(data.forecasts) ? data.forecasts : []
  const dash = data.dashboard || {}

  const byDistrict: Record<string, any[]> = {}
  for (const f of forecasts) {
    const d = f?.district
    if (!d) continue
    if (!byDistrict[d]) byDistrict[d] = []
    byDistrict[d].push(f)
  }

  for (const [district, arr] of Object.entries(byDistrict)) {
    const volume7d = sum(arr.map((x: any) => Number(x?.forecast_next_7d))) || 0
    const backlogEta = avg(arr.map((x: any) => Number(x?.backlog_eta_days))) || 0
    const satisfaction = avg(arr.map((x: any) => Number(x?.expected_satisfaction_next_7d))) || 0
    const breaches = arr.filter((x: any) => Number(x?.expected_sla_breach_rate) > 0)
    const worst = arr
      .slice()
      .sort((a: any, b: any) => Number(b?.backlog_eta_days) - Number(a?.backlog_eta_days))[0]

    dash[district] = dash[district] || {}
    dash[district].metrics = [volume7d, backlogEta, satisfaction]
    dash[district].top_factor_line = worst?.service_type
      ? `CSF-${String(worst.service_type)} (ETA: ${Number(worst.backlog_eta_days).toFixed(0)}d)`
      : `CSF-Overall (ETA: ${backlogEta.toFixed(0)}d)`
    dash[district].alert = {
      title: "Citizen Services",
      description: `${breaches.length} SLA risks • Vol(7d): ${Math.round(volume7d)}`,
    }
  }

  json.pipelines.citizenServicesFeedback.data.dashboard = dash
}

function toFeaturesForDistrict(json: any, district: string) {
  const infra = json?.pipelines?.infrastructure?.data?.[district] || {}
  const psDash = json?.pipelines?.publicSafety?.data?.dashboard?.[district] || {}
  const csfDash = json?.pipelines?.citizenServicesFeedback?.data?.dashboard?.[district] || {}

  const psMetrics: number[] = Array.isArray(psDash.metrics) ? psDash.metrics : [0, 0, 0]
  const hotspots = Number(psDash.hotspots ?? 0)
  const vol7 = Number(csfDash.metrics?.[0] ?? 0)
  const eta = Number(csfDash.metrics?.[1] ?? 0)
  const sat = Number(csfDash.metrics?.[2] ?? 0)

  return [
    Number(infra.backlog_cr ?? 0),
    Number(infra.avg_impact ?? 0),
    Number(infra.critical_roads_count ?? 0),
    Number(psMetrics[0] ?? 0),
    Number(psMetrics[1] ?? 0),
    Number(psMetrics[2] ?? 0),
    hotspots,
    vol7,
    eta,
    sat,
  ]
}

function ridgeFitPredict(X: number[][], y: number[], Xall: number[][], lambda = 1.0): number[] {
  // X: n x d, y: n, return preds for Xall: m x d
  const n = X.length
  const d = X[0]?.length || 0
  if (n === 0 || d === 0) return Xall.map(() => 0)

  // Compute XtX + lambda I and XtY
  const XtX: number[][] = Array.from({ length: d }, () => Array(d).fill(0))
  const XtY: number[] = Array(d).fill(0)
  for (let i = 0; i < n; i++) {
    const xi = X[i]
    const yi = y[i]
    for (let a = 0; a < d; a++) {
      XtY[a] += xi[a] * yi
      for (let b = 0; b < d; b++) {
        XtX[a][b] += xi[a] * xi[b]
      }
    }
  }
  for (let a = 0; a < d; a++) XtX[a][a] += lambda

  // Solve (XtX + lI) beta = XtY via Gaussian elimination
  const A: number[][] = XtX.map((row, i) => [...row, XtY[i]]) // augmented matrix d x (d+1)
  for (let col = 0; col < d; col++) {
    // pivot
    let pivot = col
    for (let r = col + 1; r < d; r++) if (Math.abs(A[r][col]) > Math.abs(A[pivot][col])) pivot = r
    if (Math.abs(A[pivot][col]) < 1e-8) continue
    if (pivot !== col) {
      const tmp = A[col]
      A[col] = A[pivot]
      A[pivot] = tmp
    }
    // normalize
    const div = A[col][col]
    for (let c = col; c <= d; c++) A[col][c] /= div
    // eliminate others
    for (let r = 0; r < d; r++) {
      if (r === col) continue
      const factor = A[r][col]
      for (let c = col; c <= d; c++) A[r][c] -= factor * A[col][c]
    }
  }
  const beta: number[] = Array(d).fill(0)
  for (let i = 0; i < d; i++) beta[i] = isFinite(A[i][d]) ? A[i][d] : 0

  return Xall.map((x) => beta.reduce((s, b, j) => s + b * x[j], 0))
}

function ensureRiskLevel(val: number): "critical" | "high" | "medium" | "low" {
  if (val >= 70) return "critical"
  if (val >= 50) return "high"
  if (val >= 30) return "medium"
  return "low"
}

function mergeDistrictKeys(...objs: any[]): string[] {
  const set = new Set<string>()
  for (const obj of objs) {
    if (obj && typeof obj === 'object') {
      for (const key in obj) {
        if (obj.hasOwnProperty(key)) set.add(key)
      }
    }
  }
  return Array.from(set)
}

function learnAndFillDistrictRisk(json: any) {
  const districts = mergeDistrictKeys(
    json?.districtRisks,
    json?.pipelines?.infrastructure?.data,
    json?.pipelines?.publicSafety?.data?.dashboard,
    json?.pipelines?.citizenServicesFeedback?.data?.dashboard
  )

  const X: number[][] = []
  const y: number[] = []
  const Xall: number[][] = []

  for (const d of districts) {
    const feats = toFeaturesForDistrict(json, d)
    Xall.push(feats)
    const label = Number(json?.districtRisks?.[d]?.risk)
    if (Number.isFinite(label)) {
      X.push(feats)
      y.push(label)
    }
  }

  let preds: number[] = Xall.map(() => NaN)
  if (X.length >= 5) {
    preds = ridgeFitPredict(X, y, Xall, 10.0)
  }

  // Write back filled risks and levels when missing
  json.districtRisks = json.districtRisks || {}
  districts.forEach((d, i) => {
    const existing = json.districtRisks[d]
    const predicted = Math.max(0, Math.min(100, preds[i] ?? NaN))
    const risk = Number(existing?.risk)
    if (!Number.isFinite(risk) && Number.isFinite(predicted)) {
      const level = ensureRiskLevel(predicted)
      json.districtRisks[d] = { ...(existing || {}), district: d, risk: predicted, level }
    } else if (existing && !existing.level && Number.isFinite(risk)) {
      existing.level = ensureRiskLevel(risk)
    }
  })
}

function synthesizeAlertsIfMissing(json: any) {
  const alertsArr: any[] = Array.isArray(json?.alerts) ? json.alerts : []
  if (alertsArr.length > 0) return
  const risks = json?.districtRisks || {}
  const top = Object.entries(risks)
    .sort((a: any, b: any) => Number(b[1]?.risk || 0) - Number(a[1]?.risk || 0))
    .slice(0, 5)
  json.alerts = top.map(([d, rec]: any, idx: number) => ({
    id: `syn-${idx}`,
    district: d,
    level: ensureRiskLevel(Number(rec?.risk || 0)),
    title: `Risk Alert: ${Math.round(Number(rec?.risk || 0))}%`,
    description: `Top factor: ${rec?.top_factor || "N/A"}`,
    trigger: rec?.top_factor || "Derived",
    actions: ["Monitor"],
    time: new Date().toISOString(),
  }))
}

export async function GET() {
  try {
    const res = await fetch(CLOUD_FUNC_URL, { cache: "no-store" })
    if (!res.ok) {
      // Fallback to local file if cloud function fails
      const filePath = path.join(process.cwd(), '..', 'get_dashboard_data.json')
      if (fs.existsSync(filePath)) {
        const localData = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
        // Apply enrichments
        localData.kpiData = buildKpis(localData)
        enrichPublicSafety(localData)
        enrichCSF(localData)
        learnAndFillDistrictRisk(localData)
        synthesizeAlertsIfMissing(localData)
        return NextResponse.json(localData)
      }
      return NextResponse.json({ error: `Upstream HTTP ${res.status}` }, { status: 502 })
    }
    const json = await res.json()

    // Predict/fill missing fields
    json.kpiData = buildKpis(json)
    enrichPublicSafety(json)
    enrichCSF(json)
    learnAndFillDistrictRisk(json)
    synthesizeAlertsIfMissing(json)

    return NextResponse.json(json)
  } catch (err: any) {
    // Fallback to local file on error
    try {
      const filePath = path.join(process.cwd(), '..', 'get_dashboard_data.json')
      if (fs.existsSync(filePath)) {
        const localData = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
        // Apply enrichments
        localData.kpiData = buildKpis(localData)
        enrichPublicSafety(localData)
        enrichCSF(localData)
        learnAndFillDistrictRisk(localData)
        synthesizeAlertsIfMissing(localData)
        return NextResponse.json(localData)
      }
    } catch (localErr) {
      // Ignore local read error
    }
    return NextResponse.json({ error: err?.message || "Failed to fetch upstream" }, { status: 500 })
  }
}
