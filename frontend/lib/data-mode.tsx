"use client"

import React, { createContext, useContext, useEffect, useMemo, useState } from "react"

export type DataModeContextValue = {
  useMock: boolean
  setUseMock: (v: boolean) => void
}

const DataModeContext = createContext<DataModeContextValue | null>(null)

const STORAGE_KEY = "mh-dashboard-use-mock"

export function DataModeProvider({ children }: { children: React.ReactNode }) {
  const [useMock, setUseMock] = useState<boolean>(false)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw != null) setUseMock(raw === "1")
    } catch {}
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, useMock ? "1" : "0")
    } catch {}
  }, [useMock])

  const value = useMemo(() => ({ useMock, setUseMock }), [useMock])

  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>
}

export function useDataMode() {
  const ctx = useContext(DataModeContext)
  if (!ctx) throw new Error("useDataMode must be used within DataModeProvider")
  return ctx
}
