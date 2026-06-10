const BASE = "https://sports.bzzoiro.com/api/v2";
const MARKET_LABELS = {
  "1x2": "1X2",
  btts: "Ambos anotan",
  over_under_15: "Over/Under 1.5",
  over_under_25: "Over/Under 2.5",
  over_under_35: "Over/Under 3.5",
  double_chance: "Doble oportunidad",
  draw_no_bet: "Empate no apuesta",
  total_corners: "Total corners",
  corners_1x2: "Corners 1X2",
  total_red_cards: "Total rojas",
  red_card: "Tarjeta roja",
};

exports.handler = async (event) => {
  const token = process.env.BZZOIRO_API_KEY || process.env.BZZOIRO_TOKEN;
  if (!token) {
    return json(503, {
      mode: "bzzoiro",
      configured: false,
      errors: ["Falta configurar BZZOIRO_API_KEY en Netlify/local."],
      events: [],
      markets_supported: Object.keys(MARKET_LABELS).map((key) => ({ key, label: MARKET_LABELS[key] })),
    });
  }

  const errors = [];
  const limit = clampInt(event.queryStringParameters?.limit, 20, 1, 40);
  const days = clampInt(event.queryStringParameters?.days, 2, 1, 7);
  const now = new Date();
  const to = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);

  const api = (path) => fetchJson(path, token, errors);
  const [live, upcoming, predictions] = await Promise.all([
    api("/events/live/"),
    api(`/events/?status=notstarted&date_from=${encodeURIComponent(now.toISOString())}&date_to=${encodeURIComponent(to.toISOString())}&limit=${limit}`),
    api(`/predictions/?date_from=${encodeURIComponent(now.toISOString())}&date_to=${encodeURIComponent(to.toISOString())}&limit=200`),
  ]);

  const predictionByEvent = new Map((predictions?.results || []).map((item) => [Number(item.event?.id), item]));
  const rawEvents = [
    ...(live?.events || []).map((item) => ({ ...item, source_window: "live" })),
    ...(upcoming?.results || []).map((item) => ({ ...item, source_window: "upcoming" })),
  ];
  const unique = dedupe(rawEvents).slice(0, limit);
  const enriched = await Promise.all(unique.map((item) => enrichEvent(item, predictionByEvent.get(Number(item.id)), api)));
  const events = enriched.map(analyzeEvent).sort((a, b) => (b.value_score || 0) - (a.value_score || 0));

  return json(200, {
    mode: "bzzoiro-v2",
    configured: true,
    updated_at: new Date().toISOString(),
    live_count: live?.count || (live?.events || []).length || 0,
    upcoming_count: upcoming?.count || (upcoming?.results || []).length || 0,
    event_count: events.length,
    errors,
    sources: {
      base_url: BASE,
      events: "/events/live/ and /events/",
      predictions: "/predictions/ and /events/{id}/prediction/",
      odds: "/events/{id}/odds/comparison/",
      stats: "/events/{id}/stats/",
      metadata: "/events/{id}/metadata/",
      lineups: "/events/{id}/lineups/",
    },
    markets_supported: Object.keys(MARKET_LABELS).map((key) => ({ key, label: MARKET_LABELS[key] })),
    events,
  });
};

async function enrichEvent(item, listPrediction, api) {
  const id = Number(item.id);
  const [detail, prediction, odds, stats, metadata, lineups] = await Promise.all([
    api(`/events/${id}/`),
    listPrediction ? Promise.resolve(listPrediction) : api(`/events/${id}/prediction/`),
    api(`/events/${id}/odds/comparison/`),
    item.status === "inprogress" || item.source_window === "live" ? api(`/events/${id}/stats/`) : Promise.resolve(null),
    api(`/events/${id}/metadata/`),
    api(`/events/${id}/lineups/`),
  ]);
  return {
    ...(detail || {}),
    ...item,
    prediction: prediction && !prediction.detail ? prediction : null,
    odds: odds && !odds.detail ? odds : { markets: {} },
    stats: stats && !stats.detail ? stats : null,
    metadata: metadata && !metadata.detail ? metadata : null,
    lineups: lineups && !lineups.detail ? lineups : null,
  };
}

function analyzeEvent(event) {
  const p = event.prediction?.markets || {};
  const rec = event.prediction?.recommendations || {};
  const match = p.match_result || {};
  const goals = p.expected_goals || {};
  const ou = p.over_under || {};
  const btts = p.btts || {};
  const score = p.score || {};
  const oddsMarkets = flattenMarkets(event.odds?.markets || {});
  const best = chooseBestMarket({ match, goals, ou, btts, rec, oddsMarkets, status: event.status });
  const statHome = event.stats?.stats?.home || null;
  const statAway = event.stats?.stats?.away || null;
  const facts = event.metadata?.funfacts?.map((item) => item.sentence).filter(Boolean).slice(0, 4) || [];
  return {
    id: event.id,
    status: event.status,
    period: event.period || null,
    current_minute: event.current_minute || null,
    time: mxTime(event.event_date),
    event_date: event.event_date,
    league_id: event.league_id,
    league: event.league_name,
    home_team: event.home_team,
    away_team: event.away_team,
    home_score: event.home_score,
    away_score: event.away_score,
    live_websocket: Boolean(event.live_websocket),
    source_window: event.source_window,
    prediction_confidence: event.prediction?.model?.confidence ?? null,
    model_version: event.prediction?.model?.version || null,
    probabilities: {
      home: probToUnit(match.prob_home),
      draw: probToUnit(match.prob_draw),
      away: probToUnit(match.prob_away),
      over15: probToUnit(ou.prob_over_15),
      over25: probToUnit(ou.prob_over_25),
      over35: probToUnit(ou.prob_over_35),
      under15: inverseProb(ou.prob_over_15),
      under25: inverseProb(ou.prob_over_25),
      under35: inverseProb(ou.prob_over_35),
      btts_yes: probToUnit(btts.prob_yes),
      btts_no: inverseProb(btts.prob_yes),
    },
    expected_goals: {
      home: toNum(goals.home),
      away: toNum(goals.away),
      total: round1(toNum(goals.home) + toNum(goals.away)),
      most_likely_score: score.most_likely || "",
    },
    recommendation: best.pick,
    best_market: best.market,
    best_probability: best.probability,
    best_odds: best.odds,
    edge: best.edge,
    value_score: best.value_score,
    confidence: best.confidence,
    odds_markets: oddsMarkets,
    markets_available: Object.keys(event.odds?.markets || {}).map((key) => ({ key, label: MARKET_LABELS[key] || key })),
    live_stats: statHome || statAway ? { home: normalizeStats(statHome), away: normalizeStats(statAway) } : null,
    lineup_status: event.lineups?.lineup_status || "unavailable",
    lineups: summarizeLineups(event.lineups),
    facts,
    analysis: buildAnalysis(event, best, { match, goals, ou, btts, score, rec, statHome, statAway, facts }),
  };
}

function chooseBestMarket({ match, ou, btts, oddsMarkets }) {
  const candidates = [];
  addCandidate(candidates, "1X2", "Local gana", probToUnit(match.prob_home), bestOdd(oddsMarkets, "1x2", "HOME"));
  addCandidate(candidates, "1X2", "Empate", probToUnit(match.prob_draw), bestOdd(oddsMarkets, "1x2", "DRAW"));
  addCandidate(candidates, "1X2", "Visita gana", probToUnit(match.prob_away), bestOdd(oddsMarkets, "1x2", "AWAY"));
  addCandidate(candidates, "Over/Under 1.5", "Over 1.5", probToUnit(ou.prob_over_15), bestOdd(oddsMarkets, "over_under_15", "over"));
  addCandidate(candidates, "Over/Under 1.5", "Under 1.5", inverseProb(ou.prob_over_15), bestOdd(oddsMarkets, "over_under_15", "under"));
  addCandidate(candidates, "Over/Under 2.5", "Over 2.5", probToUnit(ou.prob_over_25), bestOdd(oddsMarkets, "over_under_25", "over"));
  addCandidate(candidates, "Over/Under 2.5", "Under 2.5", inverseProb(ou.prob_over_25), bestOdd(oddsMarkets, "over_under_25", "under"));
  addCandidate(candidates, "Over/Under 3.5", "Over 3.5", probToUnit(ou.prob_over_35), bestOdd(oddsMarkets, "over_under_35", "over"));
  addCandidate(candidates, "Over/Under 3.5", "Under 3.5", inverseProb(ou.prob_over_35), bestOdd(oddsMarkets, "over_under_35", "under"));
  addCandidate(candidates, "BTTS", "Ambos anotan Si", probToUnit(btts.prob_yes), bestOdd(oddsMarkets, "btts", "yes"));
  addCandidate(candidates, "BTTS", "Ambos anotan No", inverseProb(btts.prob_yes), bestOdd(oddsMarkets, "btts", "no"));
  const valid = candidates.filter((item) => item.probability > 0);
  return valid.sort((a, b) => b.value_score - a.value_score)[0] || { market: "No Bet", pick: "No Bet", probability: 0, odds: null, edge: 0, value_score: 0, confidence: "Baja" };
}

function addCandidate(out, market, pick, probability, odds) {
  if (!Number.isFinite(probability) || probability <= 0) return;
  const implied = odds?.decimal_odds ? 1 / odds.decimal_odds : null;
  const edge = implied == null ? 0 : probability - implied;
  const value_score = implied == null
    ? Math.max(0, Math.min(58, probability * 70))
    : Math.max(0, Math.min(100, probability * 60 + Math.max(0, edge) * 160 + 10));
  out.push({ market, pick, probability: round3(probability), odds, edge: round3(edge), value_score: round1(value_score), confidence: value_score >= 74 ? "Alta" : value_score >= 62 ? "Media" : "Baja" });
}

function flattenMarkets(markets) {
  return Object.entries(markets || {}).map(([key, value]) => {
    const outcomes = [];
    for (const [outcome, row] of Object.entries(value || {})) {
      if (!row || typeof row !== "object") continue;
      if (row.best_odds) {
        outcomes.push({
          market: key,
          bookmaker: row.best_bookmaker_name || row.best_bookmaker_slug || "best",
          outcome,
          outcome_name: row.outcome_name || outcome,
          line: row.line ?? null,
          decimal_odds: Number(row.best_odds),
          movement: "",
          is_max_quote: true,
          updated_at: latestUpdated(row.bookmakers || {}),
        });
      }
      for (const [bookmaker, quote] of Object.entries(row.bookmakers || {})) {
        if (quote && typeof quote === "object" && quote.decimal_odds) {
          outcomes.push({
            market: key,
            bookmaker,
            outcome,
            outcome_name: row.outcome_name || outcome,
            line: row.line ?? null,
            decimal_odds: Number(quote.decimal_odds),
            movement: quote.movement || "",
            is_max_quote: false,
            updated_at: quote.updated_at || "",
          });
        }
      }
    }
    return { key, label: MARKET_LABELS[key] || key, outcomes };
  });
}

function bestOdd(markets, market, outcome) {
  const rows = markets.find((item) => item.key === market)?.outcomes.filter((item) => item.outcome === outcome) || [];
  return rows.sort((a, b) => b.decimal_odds - a.decimal_odds)[0] || null;
}

function latestUpdated(bookmakers) {
  return Object.values(bookmakers)
    .map((item) => item?.updated_at || "")
    .filter(Boolean)
    .sort()
    .at(-1) || "";
}

async function fetchJson(path, token, errors) {
  try {
    const res = await fetch(`${BASE}${path}`, { headers: { authorization: `Token ${token}`, accept: "application/json", "user-agent": "football-real-analytics/1.0" } });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`${res.status} ${path}`);
    return await res.json();
  } catch (err) {
    errors.push(err.message);
    return null;
  }
}

function buildAnalysis(event, best, ctx) {
  const live = event.status === "inprogress" ? `Partido en vivo minuto ${event.current_minute || "?"}.` : "Partido por jugar.";
  const model = event.prediction?.model ? `Modelo BSD ${event.prediction.model.version || ""}, confianza ${Math.round((event.prediction.model.confidence || 0) * 100)}%.` : "Sin prediccion BSD disponible para este evento.";
  const goals = ctx.goals ? `Goles esperados ${toNum(ctx.goals.home).toFixed(2)}-${toNum(ctx.goals.away).toFixed(2)}, marcador probable ${ctx.score?.most_likely || "sin dato"}.` : "";
  const odds = best.odds ? `Mejor cuota ${best.odds.decimal_odds} en ${best.odds.bookmaker || "book"}. Edge estimado ${Math.round(best.edge * 100)} puntos.` : "Sin cuota disponible para confirmar value.";
  const stat = ctx.statHome || ctx.statAway ? `Live stats: tiros ${ctx.statHome?.total_shots ?? "-"}-${ctx.statAway?.total_shots ?? "-"}, ataques peligrosos ${ctx.statHome?.dangerous_attack ?? "-"}-${ctx.statAway?.dangerous_attack ?? "-"}.` : "Sin live stats avanzadas en este momento.";
  const facts = ctx.facts?.length ? `Factores: ${ctx.facts.join(" ")}` : "";
  return `${live} ${model} Mejor mercado: ${best.pick} (${best.market}) con probabilidad ${Math.round(best.probability * 100)}% y value ${best.value_score}. ${odds} ${goals} ${stat} ${facts}`.trim();
}

function normalizeStats(s) {
  if (!s) return null;
  return { possession: s.ball_possession ?? null, shots: s.total_shots ?? null, shots_on_target: s.shots_on_target ?? null, attack: s.attack ?? null, dangerous_attack: s.dangerous_attack ?? null, xg: s.xg?.actual ?? null, pass_accuracy_pct: s.pass_accuracy_pct ?? null };
}

function summarizeLineups(data) {
  if (!data?.lineups) return null;
  return {
    home: { formation: data.lineups.home?.formation || "", confidence: data.lineups.home?.confidence ?? null, players: (data.lineups.home?.players || []).slice(0, 11).map((p) => p.short_name || p.name) },
    away: { formation: data.lineups.away?.formation || "", confidence: data.lineups.away?.confidence ?? null, players: (data.lineups.away?.players || []).slice(0, 11).map((p) => p.short_name || p.name) },
  };
}

function dedupe(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = Number(item.id);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function probToUnit(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n > 1 ? n / 100 : n;
}
function inverseProb(value) {
  const n = probToUnit(value);
  return n == null ? null : 1 - n;
}
function toNum(value) { const n = Number(value); return Number.isFinite(n) ? n : 0; }
function round1(n) { return Math.round((Number(n) || 0) * 10) / 10; }
function round3(n) { return Math.round((Number(n) || 0) * 1000) / 1000; }
function clampInt(value, fallback, min, max) { const n = Number.parseInt(value, 10); return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback; }
function mxTime(iso) { return iso ? new Date(iso).toLocaleTimeString("es-MX", { timeZone: "America/Mexico_City", hour: "2-digit", minute: "2-digit", hour12: false }) : ""; }
function json(statusCode, body) { return { statusCode, headers: { "content-type": "application/json", "cache-control": "no-store" }, body: JSON.stringify(body) }; }
