const { getStore } = require("@netlify/blobs");

const BASE = "https://sports.bzzoiro.com/api/v2";
const HISTORY_KEY = "football-real-picks-history";

exports.handler = async (event) => {
  try {
    if (event.httpMethod === "GET") {
      const picks = await readHistory();
      return json(200, { picks, summary: summarize(picks) });
    }

    if (event.httpMethod !== "POST") {
      return json(405, { error: "Metodo no permitido" });
    }

    const body = JSON.parse(event.body || "{}");
    if (body.action === "settle") {
      const result = await settlePicks();
      return json(200, result);
    }

    const saved = await savePick(body.event);
    return json(200, saved);
  } catch (err) {
    return json(500, { error: err.message || String(err) });
  }
};

async function savePick(event) {
  if (!event || !event.id) throw new Error("Evento invalido");
  const picks = await readHistory();
  const now = new Date().toISOString();
  const id = `${event.id}|${event.best_market || "No Bet"}|${event.recommendation || "No Bet"}`;
  const existing = picks.find((item) => item.id === id);
  const record = {
    id,
    event_id: event.id,
    saved_at: existing?.saved_at || now,
    last_seen_at: now,
    event_date: event.event_date || null,
    league: event.league || "",
    home_team: event.home_team || "",
    away_team: event.away_team || "",
    market: event.best_market || "No Bet",
    pick: event.recommendation || "No Bet",
    probability: event.best_probability ?? null,
    odds: event.best_odds?.decimal_odds ?? null,
    bookmaker: event.best_odds?.bookmaker || "",
    value_score: event.value_score ?? 0,
    confidence: event.confidence || "Baja",
    status: existing?.status || "PENDING",
    score_home: existing?.score_home ?? null,
    score_away: existing?.score_away ?? null,
    settled_at: existing?.settled_at || null,
    result_reason: existing?.result_reason || "",
    analysis: event.analysis || "",
    snapshot: slimEvent(event),
  };
  const next = existing ? picks.map((item) => (item.id === id ? { ...item, ...record } : item)) : [record, ...picks];
  await writeHistory(next.slice(0, 500));
  return { saved: true, pick: record, picks: next, summary: summarize(next) };
}

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
  return { settled, picks: next, summary: summarize(next) };
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
  } else if (pick.market.startsWith("Over/Under")) {
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
  const byMarket = {};
  for (const item of picks) {
    const key = item.market || "No Bet";
    byMarket[key] ||= { market: key, total: 0, won: 0, lost: 0, pending: 0, win_rate: 0 };
    byMarket[key].total += 1;
    if (item.status === "WON") byMarket[key].won += 1;
    if (item.status === "LOST") byMarket[key].lost += 1;
    if (item.status === "PENDING") byMarket[key].pending += 1;
  }
  for (const item of Object.values(byMarket)) {
    const resolved = item.won + item.lost;
    item.win_rate = resolved ? round1((item.won / resolved) * 100) : 0;
  }
  return {
    total,
    won,
    lost,
    pending,
    win_rate: graded ? round1((won / graded) * 100) : 0,
    roi_units: round1(roi),
    by_market: Object.values(byMarket).sort((a, b) => b.total - a.total),
  };
}

async function fetchEvent(id, token) {
  const res = await fetch(`${BASE}/events/${id}/`, { headers: { authorization: `Token ${token}`, accept: "application/json" } });
  if (!res.ok) return null;
  return res.json();
}

async function readHistory() {
  const store = picksStore();
  return (await store.get(HISTORY_KEY, { type: "json" })) || [];
}

async function writeHistory(picks) {
  const store = picksStore();
  await store.setJSON(HISTORY_KEY, picks);
}

function picksStore() {
  const siteID = process.env.BLOBS_SITE_ID || process.env.NETLIFY_SITE_ID || process.env.SITE_ID;
  const token = process.env.NETLIFY_BLOBS_TOKEN || process.env.NETLIFY_AUTH_TOKEN;
  if (siteID && token) return getStore({ name: "football-real-analytics", siteID, token });
  return getStore("football-real-analytics");
}

function slimEvent(event) {
  return {
    id: event.id,
    status: event.status,
    event_date: event.event_date,
    league: event.league,
    home_team: event.home_team,
    away_team: event.away_team,
    best_market: event.best_market,
    recommendation: event.recommendation,
    best_probability: event.best_probability,
    best_odds: event.best_odds,
    value_score: event.value_score,
    expected_goals: event.expected_goals,
    probabilities: event.probabilities,
    live_stats: event.live_stats,
  };
}

function toNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function round1(value) {
  return Math.round((Number(value) || 0) * 10) / 10;
}
function json(statusCode, body) {
  return { statusCode, headers: { "content-type": "application/json", "cache-control": "no-store" }, body: JSON.stringify(body) };
}
