import { NextRequest, NextResponse } from "next/server"

const RAW_KEY = (process.env.GEMINI_API_KEY ?? "AIzaSyAioR7ImI3LQ4BavsIuE_4weVcwJOi1tzY").trim()
const MODEL_NAME = process.env.GEMINI_MODEL || "gemini-2.5-flash"

function ensureKey() {
  if (!RAW_KEY) throw new Error("GEMINI_API_KEY missing")
  return RAW_KEY
}

function geminiUrl(key: string) {
  return `https://generativelanguage.googleapis.com/v1beta/models/${MODEL_NAME}:generateContent?key=${encodeURIComponent(key)}`
}

function bad(message: string, status = 400) {
  return NextResponse.json({ error: message }, { status })
}

// Validators
function isNonEmptyString(x: any): x is string { return typeof x === "string" && x.trim().length > 0 }
function isNumber(x: any): x is number { return typeof x === "number" && Number.isFinite(x) }

function validateDistrictAI(obj: any) {
  const actions: string[] = Array.isArray(obj?.actions) ? obj.actions.filter(isNonEmptyString) : []
  const confidence: number = Number(obj?.confidence)
  const explanation: string = String(obj?.explanation ?? "")
  
  if (!actions.length) throw new Error("Invalid AI: actions empty")
  if (!isNumber(confidence) || confidence < 0 || confidence > 1) throw new Error("Invalid AI: confidence must be number between 0-1")
  if (!isNonEmptyString(explanation)) throw new Error("Invalid AI: explanation empty")
  
  return { actions, confidence, explanation }
}

type DepartmentFactor = { name: string; status: string }
function validateDepartmentAI(obj: any) {
  if (Array.isArray(obj?.factors)) {
    const factors = obj.factors
      .filter((f: any) => isNonEmptyString(f?.name) && isNonEmptyString(f?.status))
      .map((f: any) => ({ name: String(f.name).trim(), status: String(f.status).trim() })) as DepartmentFactor[]
    if (!factors.length) throw new Error("Invalid AI: no factors")
    return { factorsByDepartment: null as any, factors }
  }
  
  const map = obj?.factorsByDepartment
  if (!Array.isArray(map)) throw new Error("Invalid AI: factorsByDepartment missing")
  
  const out: Record<string, DepartmentFactor[]> = {}
  for (const item of map) {
    const id = String(item?.id ?? "").trim()
    if (!id) continue
    const fs = Array.isArray(item?.factors) ? item.factors : []
    const parsed = fs
      .filter((f: any) => isNonEmptyString(f?.name) && isNonEmptyString(f?.status))
      .map((f: any) => ({ name: String(f.name).trim(), status: String(f.status).trim() })) as DepartmentFactor[]
    if (parsed.length) out[id] = parsed
  }
  
  if (!Object.keys(out).length) throw new Error("Invalid AI: empty mapping")
  return { factorsByDepartment: out, factors: null as any }
}

function systemPreamble() {
  return (
    "You are an assistant for a government operations dashboard. " +
    "Output must be valid JSON only. Do not include any text, markdown, or explanations outside the JSON object. " +
    "Be concise, actionable, and avoid duplication."
  )
}

async function callGeminiJSON(contents: Array<{ role: string; parts: Array<{ text: string }> }>) {
  const key = ensureKey()
  const url = geminiUrl(key)
  const payload = {
    contents,
    generationConfig: {
      temperature: 0.1, // Lower temperature for more consistent JSON
      maxOutputTokens: 1024, // Increased for better JSON completion
      responseMimeType: "application/json",
    },
  }
  
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  
  if (!resp.ok) {
    const errText = await resp.text()
    throw new Error(`Gemini HTTP ${resp.status}: ${errText}`)
  }
  
  const json = await resp.json()
  let text = json?.candidates?.[0]?.content?.parts?.[0]?.text || "{}"
  
  // Clean and extract JSON
  text = text.trim()
  // Remove markdown code blocks if present
  text = text.replace(/```json\s*|\s*```/g, '')
  // Extract JSON if wrapped in markdown or text
  const jsonMatch = text.match(/\{[\s\S]*\}/)
  if (jsonMatch) text = jsonMatch[0]
  
  return text
}

function tryNormalizeDistrict(parsed: any) {
  const out: any = { 
    actions: [], 
    confidence: parsed?.confidence ?? parsed?.score ?? 0.5, 
    explanation: parsed?.explanation ?? parsed?.reason ?? parsed?.rationale ?? "No explanation provided" 
  }

  // Try different possible action fields
  if (Array.isArray(parsed?.actions) && parsed.actions.length) {
    out.actions = parsed.actions.map((a: any) => typeof a === 'string' ? a.trim() : (a?.text || JSON.stringify(a))).filter(isNonEmptyString)
  }
  if (!out.actions.length && Array.isArray(parsed?.recommendations) && parsed.recommendations.length) {
    out.actions = parsed.recommendations.map((r: any) => (typeof r === 'string' ? r.trim() : (r?.text || JSON.stringify(r)))).filter(isNonEmptyString)
  }
  if (!out.actions.length && Array.isArray(parsed?.recommended_actions) && parsed.recommended_actions.length) {
    out.actions = parsed.recommended_actions.map((r: any) => (typeof r === 'string' ? r.trim() : (r?.text || JSON.stringify(r)))).filter(isNonEmptyString)
  }
  
  // If it's a string with numbered list or bullet points, extract lines
  if (!out.actions.length) {
    let textToParse = typeof parsed === 'string' ? parsed : JSON.stringify(parsed)
    const lines = textToParse.split(/\r?\n/).map(s => s.trim()).filter(Boolean)
    const candidates = lines
      .filter(l => /^\d+\.\s+|^-\s+|^•\s+|^\*\s+/.test(l))
      .map(l => l.replace(/^\d+\.\s*/, '').replace(/^[-•*]\s*/, '').trim())
      .filter(isNonEmptyString)
    
    if (candidates.length) out.actions = candidates
  }
  
  // Some models nest under data.actions
  if (!out.actions.length && Array.isArray(parsed?.data?.actions)) {
    out.actions = parsed.data.actions.map((a: any) => String(a).trim()).filter(isNonEmptyString)
  }
  
  // Ensure confidence is numeric and within bounds
  out.confidence = Math.max(0, Math.min(1, Number(out.confidence)))
  if (Number.isNaN(out.confidence)) out.confidence = 0.5
  
  // Fallback: if still no actions, provide a default
  if (!out.actions.length) {
    out.actions = ["Review current operational data and identify key areas for improvement"]
    out.confidence = 0.1
    out.explanation = "Unable to generate specific recommendations from provided context"
  }
  
  return out
}

function tryNormalizeDepartment(parsed: any, departments: Array<{id: string}>) {
  // If factorsByDepartment present but different shape, coerce
  if (Array.isArray(parsed?.factorsByDepartment)) {
    return { factorsByDepartment: parsed.factorsByDepartment }
  }
  
  // If root is an array of items with id & factors
  if (Array.isArray(parsed) && parsed.length) {
    const arr = parsed
      .map((it: any) => ({ 
        id: String(it?.id ?? it?.department ?? '').trim(), 
        factors: Array.isArray(it?.factors ?? it?.top_factors) ? (it.factors || it.top_factors) : [] 
      }))
      .filter((item: any) => item.id && Array.isArray(item.factors))
    
    return { factorsByDepartment: arr }
  }
  
  // If there is an object mapping ids to factors
  const candidate: Record<string, any> = {}
  let found = false
  
  for (const k of Object.keys(parsed || {})) {
    const val = parsed[k]
    if (Array.isArray(val) && val.length) {
      // Convert array of strings or objects to factors format
      const factors = val.map((f: any) => {
        if (typeof f === 'string') {
          return { name: f.trim(), status: '⚠️' }
        } else {
          return { 
            name: String(f?.name || f?.factor || JSON.stringify(f)).trim(), 
            status: String(f?.status || f?.level || '⚠️').trim() 
          }
        }
      }).filter((f: any) => isNonEmptyString(f.name))
      
      if (factors.length) {
        candidate[k] = factors
        found = true
      }
    }
  }
  
  if (found) {
    const outArr = Object.entries(candidate)
      .map(([id, factors]) => ({ id, factors }))
      .filter((item: any) => item.id && Array.isArray(item.factors) && item.factors.length)
    return { factorsByDepartment: outArr }
  }
  
  // Try nested data key
  if (parsed?.data) return tryNormalizeDepartment(parsed.data, departments)
  
  return null
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const type = String(body?.type || "") as "district" | "department"
    if (!type) return bad("Missing type")

    if (type === "district") {
      const district = String(body?.district || "")
      const context = body?.context || {}
      if (!district) return bad("Missing district")

      // Enhanced system prompt with explicit JSON schema
      const systemPrompt = `You are an AI governance advisor for district operations. Based on the current situation and data provided for the district, analyze risks, triggers, insights, departments, and alerts to generate specific, actionable recommended actions.

CRITICAL: You MUST return valid JSON with this exact structure:
{
  "actions": ["action 1", "action 2", "action 3"],
  "confidence": 0.85,
  "explanation": "Brief explanation of recommendations and confidence level"
}

RULES:
- "actions" must be an array of 3-5 specific, actionable strings tailored to the district's situation
- "confidence" must be a number between 0-1 reflecting how confident you are in the recommendations based on data quality and relevance
- "explanation" must be a string explaining the rationale for the actions and justifying the confidence score
- Do NOT include any text outside the JSON object`

      const userPrompt = `District: ${district}
Context: ${JSON.stringify(context, null, 2)}

Provide governance recommendations based on the above context.`

      const contents = [
        {
          role: "user",
          parts: [
            { text: systemPrompt },
            { text: userPrompt }
          ],
        },
      ]

      const text = await callGeminiJSON(contents)
      let parsed: any
      
      try { 
        parsed = JSON.parse(text) 
      } catch (parseError) {
        // Attempt to recover if text contains JSON
        const match = text.match(/\{[\s\S]*\}/)
        if (match) {
          try { 
            parsed = JSON.parse(match[0]) 
          } catch (e) { 
            // If still can't parse, use normalization
            parsed = tryNormalizeDistrict(text)
          }
        } else {
          // If no JSON found, use the raw text
          parsed = tryNormalizeDistrict(text)
        }
      }

      // First validation attempt
      try {
        const clean = validateDistrictAI(parsed)
        return NextResponse.json(clean)
      } catch (err: any) {
        // If validation fails, try to normalize the data
        const normalized = tryNormalizeDistrict(parsed)
        
        try {
          const cleanNormalized = validateDistrictAI(normalized)
          return NextResponse.json(cleanNormalized)
        } catch (normalizeError: any) {
          // Final fallback - return minimal valid response
          const fallbackResponse = {
            actions: ["Conduct comprehensive review of district operations and resource allocation"],
            confidence: 0.1,
            explanation: "Default recommendation due to insufficient or unparseable AI response"
          }
          return NextResponse.json(fallbackResponse)
        }
      }
    }

    if (type === "department") {
      const district = String(body?.district || "")
      const departments: Array<{ id: string; title: string }> = Array.isArray(body?.departments)
        ? body.departments.map((d: any) => ({ id: String(d?.id).trim(), title: String(d?.title).trim() })).filter((d: any) => d.id)
        : []
      const context = body?.context || {}
      
      if (!district) return bad("Missing district")
      if (!departments.length) return bad("No departments provided")

      // Enhanced department prompt
      const systemPrompt = `You are an AI department analyst. Analyze department factors and return valid JSON.

CRITICAL: Return JSON with this exact structure:
{
  "factorsByDepartment": [
    {
      "id": "dept1",
      "factors": [
        {"name": "Factor 1", "status": "🔴"},
        {"name": "Factor 2", "status": "🟡"}
      ]
    }
  ]
}

RULES:
- "factorsByDepartment" must be an array
- Each item must have "id" (matching department IDs) and "factors" array  
- Each factor must have "name" (string) and "status" (emoji: 🔴🟡🟢)
- Provide 2-3 factors per department
- Do NOT include any text outside JSON`

      const userPrompt = `District: ${district}
Departments: ${JSON.stringify(departments, null, 2)}
Context: ${JSON.stringify(context, null, 2)}

Analyze risk factors for each department.`

      const contents = [
        {
          role: "user",
          parts: [
            { text: systemPrompt },
            { text: userPrompt }
          ],
        },
      ]

      const text = await callGeminiJSON(contents)
      let parsed: any
      
      try { 
        parsed = JSON.parse(text) 
      } catch {
        const match = text.match(/\{[\s\S]*\}/)
        if (match) {
          try { parsed = JSON.parse(match[0]) } catch (e) { 
            return bad("AI response was not valid JSON", 502)
          }
        } else {
          return bad("AI response was not valid JSON", 502)
        }
      }

      try {
        const clean = validateDepartmentAI(parsed)
        return NextResponse.json(clean)
      } catch (err: any) {
        const normalized = tryNormalizeDepartment(parsed, departments)
        if (normalized) {
          try { 
            const clean2 = validateDepartmentAI(normalized)
            return NextResponse.json(clean2) 
          } catch (e) {
            // Fall through to error
          }
        }
        
        // Final fallback for department
        const fallbackResponse = {
          factorsByDepartment: departments.map(dept => ({
            id: dept.id,
            factors: [
              { name: "Operational efficiency review needed", status: "🟡" },
              { name: "Resource allocation assessment", status: "🔴" }
            ]
          }))
        }
        return NextResponse.json(fallbackResponse)
      }
    }

    return bad("Unsupported type")
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "AI call failed" }, { status: 500 })
  }
}