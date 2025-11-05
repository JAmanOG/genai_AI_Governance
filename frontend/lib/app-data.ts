/**
 * Data Catalog (single source of truth)
 *
 * Purpose: Central place to see ALL demo data and its schema. You can mirror this structure in your API.
 * How to use now: Read this file to prepare real API payloads. (No imports or code changes elsewhere.)
 *
 * Datasets and fields
 * - kpiData (object keyed by id)
 *   - value: string | number (display value)
 *   - label: string (caption for KPI)
 *   - iconName: string (Lucide icon name, e.g., AlertCircle)
 *   - color: string (Tailwind class for icon color)
 *
 * - districtRisks (object keyed by district name)
 *   - risk: number (0-100)
 *   - level: "critical" | "high" | "medium" | "low"
 *
 * - alerts (array)
 *   - id: number
 *   - district: string
 *   - level: RiskLevel
 *   - title: string
 *   - description: string
 *   - trigger: string
 *   - actions: string[]
 *   - time: string (human readable)
 *
 * - departments (array)
 *   - id: string
 *   - iconName: string (Lucide icon name)
 *   - title: string
 *   - color: string (Tailwind class for icon color)
 *   - metrics: { label: string; value: string; status?: string }[]
 *   - factors: { name: string; status: string }[]
 */

export type RiskLevel = "critical" | "high" | "medium" | "low"

export type KPI = {
  value: string | number
  label: string
  iconName: string
  color: string
}

export type KPIData = {
  critical: KPI
  highRisk: KPI
  population: KPI
  budget: KPI
}

export type DistrictRisks = Record<string, { risk: number; level: RiskLevel }>

export type AlertItem = {
  id: string | number
  district: string
  level: RiskLevel
  title: string
  description: string
  trigger: string
  actions: string[]
  time: string
}

export type DepartmentMetric = { label: string; value: string; status?: string }
export type DepartmentFactor = { name: string; status: string }
export type Department = {
  id: string
  iconName: string
  title: string
  color: string
  metrics: DepartmentMetric[]
  factors: DepartmentFactor[]
}

export type AppData = {
  kpiData: KPIData
  districtRisks: DistrictRisks
  alerts: AlertItem[]
  departments: Department[]
  pipelines?: any
}

export const kpiData: KPIData = {
  critical: {
    value: 3,
    label: "CRITICAL ALERTS",
    iconName: "AlertCircle",
    color: "text-destructive",
  },
  highRisk: {
    value: "5/36",
    label: "HIGH RISK DISTRICTS",
    iconName: "TrendingUp",
    color: "text-orange-500",
  },
  population: {
    value: "2.4M",
    label: "AFFECTED POPULATION",
    iconName: "Users",
    color: "text-blue-500",
  },
  budget: {
    value: "₹142 Cr",
    label: "BUDGET IMPACT",
    iconName: "DollarSign",
    color: "text-amber-500",
  },
}

export const districtRisks: DistrictRisks = {
  Pune: { risk: 82, level: "critical" },
  Mumbai: { risk: 45, level: "medium" },
  Nagpur: { risk: 23, level: "low" },
  Thane: { risk: 67, level: "high" },
  Nashik: { risk: 38, level: "medium" },
  Aurangabad: { risk: 55, level: "high" },
}

export const alerts: AlertItem[] = [
  {
    id: 1,
    district: "Pune District",
    level: "critical",
    title: "Outbreak Risk: 82%",
    description: "ETA: 10-14 days",
    trigger: "Rising PM2.5 + Waste Management Issues",
    actions: ["Deploy Health Teams", "Sanitation Drive"],
    time: "2 hours ago",
  },
  {
    id: 2,
    district: "Thane Infrastructure",
    level: "high",
    title: "Road Repair Probability: 78%",
    description: "Critical Roads: 12",
    trigger: "Monsoon Damage + High Traffic",
    actions: ["Schedule Repairs", "Traffic Diversion"],
    time: "4 hours ago",
  },
  {
    id: 3,
    district: "Mumbai Public Safety",
    level: "medium",
    title: "Crime Hotspot Alert: Sector 5, 7",
    description: "Trend: 25% increase in theft",
    trigger: "Theft incidents rising",
    actions: ["Increase Patrols", "Community Alert"],
    time: "6 hours ago",
  },
]

export const departments: Department[] = [
  {
    id: "health",
    iconName: "Heart",
    title: "Health & Disease Control",
    color: "text-red-500",
    metrics: [
      { label: "Outbreak Risk", value: "82%", status: "⬆️ 15%" },
      { label: "Patient Load", value: "2,340/day" },
      { label: "Vaccine Coverage", value: "78%", status: "✅" },
      { label: "Response Time", value: "22 min" },
    ],
    factors: [
      { name: "PM2.5 Levels (58 μg/m³)", status: "❌" },
      { name: "Waste Collection (65%)", status: "❌" },
      { name: "Water Quality Index (72)", status: "⚠️" },
    ],
  },
  {
    id: "infrastructure",
    iconName: "Building2",
    title: "Infrastructure & Roads",
    color: "text-orange-500",
    metrics: [
      { label: "Condition Score", value: "6.2/10", status: "⚠️" },
      { label: "Repair Backlog", value: "₹45 Cr" },
      { label: "Traffic Impact", value: "42K vehicles" },
      { label: "Budget", value: "₹120 Cr" },
    ],
    factors: [
      { name: "Pune-Mumbai Highway (Urgency: 89%)", status: "🔴" },
      { name: "Nagpur Ring Road (Condition: 4.2/10)", status: "🟠" },
    ],
  },
  {
    id: "safety",
    iconName: "Shield",
    title: "Public Safety & Crime",
    color: "text-blue-500",
    metrics: [
      { label: "Crime Rate", value: "12.4/1K", status: "⬆️ 8%" },
      { label: "Response Time", value: "18.2 min", status: "✅" },
      { label: "Cases Resolved", value: "78%", status: "✅" },
      { label: "Hotspots", value: "3" },
    ],
    factors: [
      { name: "Theft: Sector 5 (42 incidents)", status: "📈" },
      { name: "Fraud: Digital (15 cases)", status: "📈" },
    ],
  },
  {
    id: "citizen",
    iconName: "Users",
    title: "Citizen Services & Feedback",
    color: "text-green-500",
    metrics: [
      { label: "Request Volume", value: "1,240/day" },
      { label: "Avg Resolution", value: "2.3 days", status: "✅" },
      { label: "Satisfaction", value: "8.2/10", status: "✅" },
      { label: "Pending", value: "342" },
    ],
    factors: [
      { name: "Water Supply (45%)", status: "💧" },
      { name: "Road Repair (28%)", status: "🛣️" },
      { name: "Waste Management (18%)", status: "🗑️" },
    ],
  },
]

/**
 * Full dataset in one object (API-friendly)
 */
export const appData: AppData = {
  kpiData,
  districtRisks,
  alerts,
  departments,
  pipelines: undefined,
}

/**
 * JSON helper if you need a deep-cloned plain object (e.g., for serializing or mocking an API response)
 */
export const getAppDataJson = (): AppData => JSON.parse(JSON.stringify(appData))
