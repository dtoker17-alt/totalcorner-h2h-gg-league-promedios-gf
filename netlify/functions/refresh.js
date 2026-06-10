const LEAGUES = [
  { id: "h2hgg", name: "Esoccer H2H GG League - 8 mins", url: "https://www.totalcorner.com/league/view/37552", mode: "ou_only" },
  { id: "gt", name: "Esoccer GT Leagues - 12 mins", url: "https://www.totalcorner.com/league/view/12985", mode: "1x2_only" },
  { id: "battle", name: "Esoccer Battle - 8 mins", url: "https://www.totalcorner.com/league/view/12995", mode: "1x2_only" },
  { id: "volta", name: "Esoccer Battle Volta - 6 mins", url: "https://www.totalcorner.com/league/view/38895", mode: "1x2_only" }
];

exports.handler = async () => {
  const errors = [];
  const pages = {};
  for (const league of LEAGUES) {
    try {
      pages[league.id] = await fetch(league.url, { headers: { "user-agent": "Mozilla/5.0" } }).then(r => r.text());
    } catch (err) {
      errors.push(`${league.id}: ${err.message}`);
    }
  }
  const stats = {};
  for (const league of LEAGUES) parseStats(league, pages[league.id] || "", stats);
  const fixtures = await h2hFixtures(errors);
  fixtures.push(...await esportsBattleFixtures(stats, errors));
  for (const league of LEAGUES.filter(l => l.id !== "h2hgg")) fixtures.push(...tcLiveFixtures(league, pages[league.id] || ""));
  const unique = dedupe(fixtures);
  const matches = unique.map(f => analyze(f, stats)).filter(Boolean).sort((a,b)=>rank(b)-rank(a));
  return json({ updated_at: new Date().toISOString(), mode: "precision-netlify", fixture_count: unique.length, errors, matches });
};

async function h2hFixtures(errors) {
  try {
    const rows = await fetch("https://api-h2h.hudstats.com/v1/schedule/upcoming/fifa", { headers: { origin: "https://h2hggl.com", referer: "https://h2hggl.com/", "user-agent": "Mozilla/5.0" } }).then(r => r.json());
    return rows.slice(0, 32).map(r => ({ id: r.externalId, league_id: "h2hgg", league: LEAGUES[0].name, market_mode: "ou_only", time: mxTime(r.startDate), home_player: clean(r.participantAName), away_player: clean(r.participantBName), home_team: r.teamAName, away_team: r.teamBName }));
  } catch (err) {
    errors.push(`h2h api: ${err.message}`);
    return [];
  }
}

function tcLiveFixtures(league, html) {
  const out = [];
  const now = Date.now();
  const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = rowRe.exec(html))) {
    const cols = [...m[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(x => strip(x[1]));
    if (cols.length < 5 || /^Full$/i.test(cols[1])) continue;
    const hp = splitPlayer(cols[2]), ap = splitPlayer(cols[4]);
    if (!hp.player || !ap.player) continue;
    const start = totalCornerDate(cols[0]);
    const delta = start.getTime() - now;
    if (!Number.isFinite(delta) || delta < -8 * 60 * 1000 || delta > 75 * 60 * 1000) continue;
    out.push({ id: `${league.id}|${cols[0]}|${hp.player}|${ap.player}`, league_id: league.id, league: league.name, market_mode: league.mode, time: mxTime(start), room: "TotalCorner live", home_player: hp.player, away_player: ap.player, home_team: hp.team, away_team: ap.team });
  }
  return out.slice(0, 8);
}

async function esportsBattleFixtures(stats, errors) {
  try {
    const rows = await fetch("https://football.esportsbattle.com/api/tournaments/nearest-matches", { headers: { "user-agent": "Mozilla/5.0", accept: "application/json" } }).then(r => r.json());
    const leagues = LEAGUES.filter(l => l.id !== "h2hgg");
    const now = Date.now();
    return rows.map(row => {
      const hp = clean(row.participant1?.nickname), ap = clean(row.participant2?.nickname);
      const league = leagues.find(l => stats[key(l.id, hp)] && stats[key(l.id, ap)]);
      if (!league) return null;
      const start = new Date(row.date);
      const delta = start.getTime() - now;
      if (!Number.isFinite(delta) || delta < -8 * 60 * 1000 || delta > 120 * 60 * 1000) return null;
      const location = row.location?.token_international || "ESportsBattle";
      const consoleName = row.console?.token_international || "";
      return { id: `esb|${row.id}`, league_id: league.id, league: league.name, market_mode: league.mode, time: mxTime(row.date), room: `ESportsBattle ${location} ${consoleName}`.trim(), home_player: hp, away_player: ap, home_team: row.participant1?.team?.token_international || "", away_team: row.participant2?.team?.token_international || "" };
    }).filter(Boolean);
  } catch (err) {
    errors.push(`esportsbattle: ${err.message}`);
    return [];
  }
}

function dedupe(fixtures) {
  const seen = new Set();
  return fixtures.filter(f => {
    const k = `${f.league_id}|${f.time}|${f.home_player}|${f.away_player}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

function parseStats(league, html, stats) {
  const tables = [...html.matchAll(/<table[^>]*stats_table[^>]*>([\s\S]*?)<\/table>/g)].map(m => m[1]);
  if (!tables[0]) return;
  for (const row of rows(tables[0]).slice(1)) {
    const c = cells(row); if (c.length < 11) continue;
    const player = clean(c[1]); const games = +c[2] || 0; if (!player || !games) continue;
    stats[key(league.id, player)] = { player, games, wins:+c[3]||0, draws:+c[4]||0, gf:+c[8]||0, ga:+c[9]||0, dapg:+c[10]||0, over25:0.5 };
  }
  if (!tables[1]) return;
  for (const row of rows(tables[1]).slice(1)) {
    const c = cells(row); if (c.length < 7) continue;
    const player = clean(c[1]); const s = stats[key(league.id, player)]; if (s) s.over25 = pct(c[6]);
  }
}

function analyze(f, stats) {
  const h = stats[key(f.league_id, f.home_player)], a = stats[key(f.league_id, f.away_player)];
  if (!h || !a) return null;
  const homeExp = Math.max(.05, (h.gf + a.ga) / 2), awayExp = Math.max(.05, (a.gf + h.ga) / 2);
  const total = homeExp + awayExp;
  const pOver15 = poissonOver(total, 1.5);
  const pOver25 = poissonOver(total, 2.5);
  const goalTrend = clamp(scale(total, 1.8, 3.8) * 30 + h.over25 * 20 + a.over25 * 20 + scale((h.gf+a.gf+h.ga+a.ga)/2,1.4,3.4)*15 + 5, 0, 100);
  const homePower = power(h, a, true), awayPower = power(a, h, false);
  const drawRisk = clamp(50*.25 + Math.max(0,100-Math.abs(homePower-awayPower)*5)*.2 + (1-pOver25)*10, 0, 100);
  const edge = homePower - awayPower;
  const probs = winnerProbabilities(edge, drawRisk);
  let best_market = "No Bet", best_pick = "No Bet precision", prob = Math.max(pOver25, 1-pOver25), value = 34, confidence = "Baja";
  if (f.market_mode === "ou_only") {
    if (goalTrend >= 76) [best_market,best_pick,prob,value,confidence] = ["Over/Under 2.5","Over 2.5",pOver25,goalTrend,"Alta"];
    else if (goalTrend <= 28) [best_market,best_pick,prob,value,confidence] = ["Over/Under 2.5","Under 2.5",1-pOver25,100-goalTrend,"Alta"];
  } else {
    if (edge >= 18 && drawRisk < 58) [best_market,best_pick,prob,value,confidence] = ["1X2","Local gana",probs.home,50+edge,"Alta"];
    if (edge <= -18 && drawRisk < 58) [best_market,best_pick,prob,value,confidence] = ["1X2","Visita gana",probs.away,50-edge,"Alta"];
  }
  return { ...f, best_market, best_pick, best_probability: prob, value_score: Math.round(value*10)/10, confidence, expected_goals: round1(total), probability_home: round3(probs.home), probability_draw: round3(probs.draw), probability_away: round3(probs.away), probability_over15: round3(pOver15), probability_over25: round3(pOver25), probability_under25: round3(1-pOver25), goal_trend_score: round1(goalTrend), winner_score_home: round1(homePower), winner_score_away: round1(awayPower), draw_risk_score: round1(drawRisk), home_stats: publicStats(h), away_stats: publicStats(a), risk: best_pick.startsWith("No Bet") ? "filtrado precision" : "controlado", argument: `${h.player} ${h.gf}GF/${h.ga}GA vs ${a.player} ${a.gf}GF/${a.ga}GA. Modelo sin cuotas; ranking por edge estadistico.` };
}

function power(t,o,home){return scale(t.gf,.6,4.5)*18 + scale(4.8-t.ga,.4,4.4)*18 + (t.wins/Math.max(t.games,1))*22 + scale(t.gf-o.ga+2,0,5)*24 + (home?6:0) + 12}
function winnerProbabilities(edge, drawRisk){const draw=clamp(.12+(drawRisk/100)*.22, .1, .38); const remain=1-draw; const homeShare=clamp(.5+edge/120, .12, .88); return {home: remain*homeShare, draw, away: remain*(1-homeShare)}}
function publicStats(t){return {games:t.games,wins:t.wins,draws:t.draws,gf:round1(t.gf),ga:round1(t.ga),over25:round3(t.over25)}}
function round1(n){return Math.round((n||0)*10)/10}
function round3(n){return Math.round((n||0)*1000)/1000}
function poissonOver(lambda,line){let c=0;for(let k=0;k<=Math.floor(line);k++)c+=Math.exp(-lambda)*Math.pow(lambda,k)/fact(k);return clamp(1-c,0,1)}
function fact(n){return n<=1?1:n*fact(n-1)}
function scale(v,l,h){return clamp((v-l)/(h-l),0,1)}
function clamp(v,l,h){return Math.max(l,Math.min(h,v))}
function rows(t){return [...t.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)].map(m=>m[1])}
function cells(r){return [...r.matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/g)].map(m=>strip(m[1]))}
function strip(s){return s.replace(/<[^>]+>/g," ").replace(/&nbsp;/g," ").replace(/\s+/g," ").trim()}
function splitPlayer(s){const m=s.match(/^(.*?)\s*\(([^)]+)\)/);return m?{team:m[1].trim(),player:clean(m[2])}:{team:s,player:""}}
function clean(s){return String(s||"").trim().toUpperCase().replace(/\s+/g," ")}
function key(l,p){return `${l}|${clean(p)}`}
function pct(s){return (+String(s).replace("%","")||0)/100}
function mxTime(iso){return new Date(iso).toLocaleTimeString("es-MX",{timeZone:"America/Mexico_City",hour:"2-digit",minute:"2-digit",hour12:false})}
function totalCornerDate(s){const m=String(s||"").match(/(\d\d)\/(\d\d)\s+(\d\d):(\d\d)/);if(!m)return new Date(NaN);return new Date(Date.UTC(new Date().getUTCFullYear(),+m[1]-1,+m[2],+m[3],+m[4]))}
function rank(m){return (m.best_pick.startsWith("No Bet")?0:1000)+m.value_score}
function json(body){return { statusCode: 200, headers: { "content-type": "application/json", "cache-control": "no-store" }, body: JSON.stringify(body) }}
