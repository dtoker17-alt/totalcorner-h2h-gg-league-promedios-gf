import { getStore } from "@netlify/blobs";

const BASE = "https://sports.bzzoiro.com/api/v2";
const HISTORY_KEY = "football-real-picks-history";

export default async () => {
  try {
    const result = await settlePicks();
    console.log("auto-settle complete", {
      settled: result.settled,
      pending: result.summary?.pending,
      won: result.summary?.won,
      lost: result.summary?.lost,
    });
    return json(200, {
      settled: result.settled,
      summary: result.summary,
      updated_at: new Date().toISOString(),
    });
  } catch (err) {
    console.error("auto-settle failed", err);
    return json(500, { error: err.message || String(err) });
  }
};

async function settlePicks() {
  const token = process.env.BZZOIRO_API_KEY || process.env.BZZOIRO_TOKEN;
  if (!token) throw new Error("Falta configurar BZZOIRO_API_KEY");
  const picks = await readHistory();
  let settled = 0;
  const now = new Date().toISOString();
  const next = [];
  for (const pick of picks) {
    if (pick.status !== "PENDING") {
      next.push(pick);
      continue;
    }
    const detail = await fetchEvent(pick.event_id, token);
    const graded = gradePick(pick, detail);
    if (!graded) {
      next.push(pick);
      continue;
    }
    settled += 1;
    next.push({
      ...pick,
      status: graded.status,
      score_home: graded.home,
      score_away: graded.away,
      settled_at: now,
      result_reason: graded.reason,
    });
  }
  await writeHistory(next);
  return { settled, summary: summarize(next) };
}

function gradePick(pick, event) {
  if (!event) return null;
  const home = toNum(event.home_score);
  const away = toNum(event.away_score);
  if (home == null || away == null) return null;
  const status = String(event.status || "").toLowerCase();
  const finalStatus = ["finished", "fulltime", "completed", "ended", "after_penalties", "afterextra"].some((item) => status.includes(item));
  const kickoff = event.event_date ? new Date(event.event_date).getTime() : 0;
  if (!finalStatus && Date.now() - kickoff < 150 * 60 * 1000) return null;

  const total = home + away;
  const text = `${pick.market} ${pick.pick}`.toLowerCase();
  let won = null;
  if (pick.market === "1X2") {
    if (pick.pick === "Local gana") won = home > away;
    else if (pick.pick === "Empate") won = home === away;
    else if (pick.pick === "Visita gana") won = away > home;
  } else if (pick.market?.startsWith("Over/Under")) {
    const line = Number((pick.market.match(/(\d+(?:\.\d+)?)/) || [])[1]);
    if (Number.isFinite(line)) {
      if (text.includes("over")) won = total > line;
      if (text.includes("under")) won = total < line;
    }
  } else if (pick.market === "BTTS") {
    if (text.includes(" si")) won = home > 0 && away > 0;
    if (text.includes(" no")) won = home === 0 || away === 0;
  }
  if (won == null) return { status: "VOID", home, away, reason: "Mercado no liquidable automaticamente" };
  return { status: won ? "WON" : "LOST", home, away, reason: `${home}-${away}` };
}

function summarize(picks) {
  const total = picks.length;
  const won = picks.filter((item) => item.status === "WON").length;
  const lost = picks.filter((item) => item.status === "LOST").length;
  const pending = picks.filter((item) => item.status === "PENDING").length;
  const graded = won + lost;
  const roi = picks.reduce((sum, item) => {
    if (item.status === "WON") return sum + ((Number(item.odds) || 1) - 1);
    if (item.status === "LOST") return sum - 1;
    return sum;
  }, 0);
  return { total, won, lost, pending, win_rate: graded ? round1((won / graded) * 100) : 0, roi_units: round1(roi) };
}

async function fetchEvent(id, token) {
  const res = await fetch(`${BASE}/events/${id}/`, { headers: { authorization: `Token ${token}`, accept: "application/json" } });
  if (!res.ok) return null;
  return res.json();
}

async function readHistory() {
  return (await picksStore().get(HISTORY_KEY, { type: "json" })) || [];
}

async function writeHistory(picks) {
  await picksStore().setJSON(HISTORY_KEY, picks);
}

function picksStore() {
  const siteID = process.env.BLOBS_SITE_ID || process.env.NETLIFY_SITE_ID || process.env.SITE_ID;
  const token = process.env.NETLIFY_BLOBS_TOKEN || process.env.NETLIFY_AUTH_TOKEN;
  if (siteID && token) return getStore({ name: "football-real-analytics", siteID, token });
  return getStore("football-real-analytics");
}

function toNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function round1(value) {
  return Math.round((Number(value) || 0) * 10) / 10;
}
function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
