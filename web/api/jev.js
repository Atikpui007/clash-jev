// The "Re-ask Jev" panel of a replay calls this. The TypeSafe API does not accept calls made straight from a web
// page, so the request is passed on from here with the visitor's own key. The key and the request are used for that
// one call only: nothing is logged and nothing is kept.
export const config = { runtime: "edge" }

const API = "https://api.typesafe.ai/v1/systemone"
const LARGEST_REQUEST = 400_000 // a full state with its questions is about 40 kB

export default async function handler(request) {
  if (request.method !== "POST") return answer(405, { error: "POST only" })
  const origin = request.headers.get("origin")
  if (origin && new URL(origin).host !== new URL(request.url).host) return answer(403, { error: "this page only" })
  const key = request.headers.get("authorization")
  if (!key) return answer(401, { error: "a TypeSafe API key is needed" })
  const body = await request.text()
  if (body.length > LARGEST_REQUEST) return answer(413, { error: "request too large" })
  let asked
  try {
    asked = JSON.parse(body)
  } catch {
    return answer(400, { error: "the request is not JSON" })
  }
  if (!asked || typeof asked.questions !== "object" || Object.keys(asked.questions ?? {}).length !== 1)
    return answer(400, { error: "one question per request" })
  const reply = await fetch(API, {
    method: "POST",
    headers: { Authorization: key, "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ state: asked.state, model: "jev-latest", questions: asked.questions }),
  })
  return new Response(await reply.text(), { status: reply.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } })
}

function answer(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } })
}
