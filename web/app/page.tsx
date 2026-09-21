"use client"

import dynamic from "next/dynamic"

// Which mode, run and moment to open comes from the link, which only the browser knows: no server-side render.
const App = dynamic(() => import("@/components/replay/app"), { ssr: false })

export default function Page() {
  return <App />
}
