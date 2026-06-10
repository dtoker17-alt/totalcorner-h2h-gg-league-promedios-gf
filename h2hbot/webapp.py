from __future__ import annotations

import argparse

from flask import Flask, jsonify, render_template_string

from .data_service import load_dashboard
from .settings import load_settings
from .training import TrainingStore, run_training_cycle

app = Flask(__name__)


@app.get("/")
def index():
    return render_template_string(HTML)


@app.get("/api/refresh")
def refresh():
    settings = load_settings()
    data = load_dashboard(settings)
    data["training"] = TrainingStore(settings.picks_xlsx).summary()
    return jsonify(data)


@app.post("/api/train")
def train():
    settings = load_settings()
    return jsonify(run_training_cycle(settings))


def main() -> None:
    parser = argparse.ArgumentParser(description="H2H GG mobile web app")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>H2H GG Picks</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101214;
      --panel: #191d20;
      --panel-2: #20262a;
      --text: #f4f5f2;
      --muted: #a9b0b5;
      --line: #313940;
      --green: #2fd17c;
      --amber: #f2bd4b;
      --red: #ff6b6b;
      --blue: #65b7ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }
    .app { width: min(960px, 100%); margin: 0 auto; padding: 14px 12px 28px; }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      margin: -14px -12px 12px;
      padding: 12px;
      background: rgba(16,18,20,.96);
      border-bottom: 1px solid var(--line);
    }
    .topbar { display: flex; gap: 10px; align-items: center; justify-content: space-between; }
    .actions { display: flex; gap: 8px; align-items: center; }
    h1 { margin: 0; font-size: 20px; font-weight: 800; }
    .sub { margin-top: 4px; color: var(--muted); font-size: 12px; }
    button {
      border: 0;
      border-radius: 8px;
      padding: 12px 14px;
      min-width: 132px;
      background: var(--green);
      color: #06110b;
      font-weight: 800;
      font-size: 14px;
      cursor: pointer;
    }
    button:disabled { opacity: .65; cursor: wait; }
    .secondary { background: #26313a; color: var(--text); border: 1px solid var(--line); }
    .status {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin: 12px 0;
    }
    .metric { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    .metric b { display: block; font-size: 17px; }
    .metric span { color: var(--muted); font-size: 11px; }
    .alerts { display: none; background: #2a1d1d; border: 1px solid #673131; border-radius: 8px; color: #ffdada; padding: 10px; margin-bottom: 10px; font-size: 12px; }
    .sources { background: #12171a; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); padding: 10px; margin-bottom: 10px; font-size: 11px; line-height: 1.45; }
    .list { display: grid; gap: 10px; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    .card-head { display: flex; justify-content: space-between; gap: 10px; padding: 12px; border-bottom: 1px solid var(--line); }
    .teams { min-width: 0; }
    .teams .match { font-size: 16px; font-weight: 800; line-height: 1.25; }
    .teams .meta { margin-top: 4px; color: var(--muted); font-size: 12px; }
    .badge { align-self: start; border-radius: 999px; padding: 6px 9px; font-size: 12px; font-weight: 800; color: #06110b; background: var(--amber); white-space: nowrap; }
    .badge.Alta { background: var(--green); }
    .badge.Baja { background: var(--red); color: #240707; }
    .best { padding: 10px 12px; background: var(--panel-2); display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .best .pick { font-size: 18px; font-weight: 900; }
    .best .prob { color: var(--green); font-weight: 900; font-size: 18px; }
    .analysis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 10px 12px 0; }
    .chip { background: #14191c; border: 1px solid var(--line); border-radius: 8px; padding: 8px; min-width: 0; }
    .chip strong { display: block; font-size: 11px; color: var(--muted); }
    .chip span { display: block; margin-top: 3px; font-size: 14px; font-weight: 800; }
    .warning { margin: 10px 12px 0; border: 1px solid #7d5a20; background: #271f11; color: #ffe2a3; border-radius: 8px; padding: 8px; font-size: 12px; line-height: 1.35; }
    .markets { display: grid; grid-template-columns: 1fr; gap: 8px; padding: 10px 12px 12px; }
    .market { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    .market-title { padding: 8px 10px; color: var(--muted); font-size: 12px; background: #15191c; }
    .options { display: grid; grid-template-columns: repeat(3, 1fr); }
    .options.two { grid-template-columns: repeat(2, 1fr); }
    .opt { padding: 9px 8px; border-right: 1px solid var(--line); min-width: 0; }
    .opt:last-child { border-right: 0; }
    .opt strong { display: block; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .opt span { display: block; margin-top: 4px; color: var(--blue); font-size: 15px; font-weight: 800; }
    .notes { color: var(--muted); font-size: 11px; padding: 0 12px 12px; line-height: 1.4; }
    .empty { text-align: center; color: var(--muted); padding: 40px 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
    @media (min-width: 720px) {
      .markets { grid-template-columns: 1fr 1fr; }
      .status { grid-template-columns: repeat(4, 1fr); }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="topbar">
        <div>
          <h1>H2H GG Picks</h1>
          <div class="sub" id="updated">Sin actualizar</div>
        </div>
        <div class="actions">
          <button id="refreshBtn">Actualizar datos</button>
          <button id="trainBtn" class="secondary">Entrenar</button>
        </div>
      </div>
    </header>

    <section class="status">
      <div class="metric"><b id="m-count">0</b><span>Partidos</span></div>
      <div class="metric"><b id="m-tc">0</b><span>TotalCorner</span></div>
      <div class="metric"><b id="m-api">0</b><span>H2H API</span></div>
      <div class="metric"><b id="m-top">0</b><span>Mejor value</span></div>
      <div class="metric"><b id="m-wr">0%</b><span>Win rate</span></div>
      <div class="metric"><b id="m-pending">0</b><span>Pendientes</span></div>
      <div class="metric"><b id="m-strong">0</b><span>Picks fuertes</span></div>
    </section>

    <div class="sources" id="sources">Fuentes pendientes.</div>
    <div class="alerts" id="alerts"></div>
    <main class="list" id="matches"><div class="empty">Pulsa actualizar datos.</div></main>
  </div>

  <script>
    const btn = document.getElementById('refreshBtn');
    const trainBtn = document.getElementById('trainBtn');
    const matches = document.getElementById('matches');
    const alerts = document.getElementById('alerts');
    const pct = (n) => `${Math.round((n || 0) * 100)}%`;

    btn.addEventListener('click', refresh);
    trainBtn.addEventListener('click', train);
    window.addEventListener('load', refresh);

    async function refresh() {
      btn.disabled = true;
      btn.textContent = 'Actualizando...';
      try {
        const res = await fetch('/api/refresh', { cache: 'no-store' });
        const data = await res.json();
        render(data);
      } catch (err) {
        alerts.style.display = 'block';
        alerts.textContent = `Error actualizando: ${err}`;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Actualizar datos';
      }
    }

    async function train() {
      trainBtn.disabled = true;
      trainBtn.textContent = 'Entrenando...';
      try {
        const res = await fetch('/api/train', { method: 'POST' });
        const data = await res.json();
        alerts.style.display = 'block';
        alerts.innerHTML = `Entrenamiento: ${data.added} picks nuevos, ${data.settled} liquidados.`;
        await refresh();
      } catch (err) {
        alerts.style.display = 'block';
        alerts.textContent = `Error entrenando: ${err}`;
      } finally {
        trainBtn.disabled = false;
        trainBtn.textContent = 'Entrenar';
      }
    }

    function render(data) {
      document.getElementById('updated').textContent = `Actualizado ${new Date(data.updated_at).toLocaleString()} (${data.timezone})`;
      document.getElementById('m-count').textContent = data.fixture_count;
      document.getElementById('m-tc').textContent = data.stat_players_totalcorner;
      document.getElementById('m-api').textContent = data.stat_players_h2h;
      document.getElementById('m-top').textContent = data.matches.length ? Math.round(data.matches[0].value_score || 0) : '0';
      const overall = data.training && data.training.overall ? data.training.overall : {};
      document.getElementById('m-wr').textContent = pct(overall.win_rate || 0);
      document.getElementById('m-pending').textContent = overall.pending || 0;
      document.getElementById('m-strong').textContent = data.matches.filter(m => !String(m.best_pick).startsWith('No Bet')).length;
      document.getElementById('sources').innerHTML = `
        <b>Fuentes reales:</b> ${escapeHtml(data.sources.fixtures)}<br>
        <b>Stats recientes:</b> ${escapeHtml(data.sources.recent_stats)}<br>
        <b>Respaldo:</b> ${escapeHtml(data.sources.fallback_stats)}<br>
        <b>Cuotas:</b> ${escapeHtml(data.sources.odds)}<br>
        <b>Modo:</b> ${escapeHtml(data.mode || 'normal')} - filtra picks debiles para buscar mayor acierto
      `;

      if (data.errors && data.errors.length) {
        alerts.style.display = 'block';
        alerts.innerHTML = data.errors.map(e => `<div>${escapeHtml(e)}</div>`).join('');
      } else {
        alerts.style.display = 'none';
        alerts.textContent = '';
      }

      if (!data.matches.length) {
        matches.innerHTML = '<div class="empty">No hay partidos con datos suficientes.</div>';
        return;
      }

      matches.innerHTML = data.matches.map(card).join('');
    }

    function card(m) {
      return `
        <article class="card">
          <div class="card-head">
            <div class="teams">
              <div class="match">${escapeHtml(m.home_player)} vs ${escapeHtml(m.away_player)}</div>
              <div class="meta">${escapeHtml(m.league)}</div>
              <div class="meta">${m.time} - ${escapeHtml(m.room)} - ${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)} - gE ${m.home_goals_exp}-${m.away_goals_exp}</div>
            </div>
            <div class="badge ${m.confidence}">${m.confidence} - Muestra ${m.sample_quality}</div>
          </div>
          <div class="best">
            <div><div class="meta">Mejor mercado: ${escapeHtml(m.best_market)}</div><div class="pick">${escapeHtml(m.best_pick)}</div></div>
            <div class="prob">${Math.round(m.value_score || 0)}</div>
          </div>
          <div class="analysis">
            ${chip('goalTrendScore', m.goal_trend_score)}
            ${chip('drawRiskScore', m.draw_risk_score)}
            ${chip('Power local', m.winner_score_home)}
            ${chip('Power visita', m.winner_score_away)}
          </div>
          ${m.false_over_alert ? `<div class="warning">${escapeHtml(m.false_over_alert)}</div>` : ''}
          <div class="markets">
            ${m.market_mode === '1x2_only' ? `<div class="market">
              <div class="market-title">1X2</div>
              <div class="options">
                ${opt('Local', m.p_home)}
                ${opt('Empate', m.p_draw)}
                ${opt('Visitante', m.p_away)}
              </div>
            </div>` : ''}
            ${m.market_mode === 'ou_only' ? `<div class="market">
              <div class="market-title">Over / Under 2.5 goles</div>
              <div class="options two">
                ${opt('Over 2.5', m.p_over25)}
                ${opt('Under 2.5', m.p_under25)}
              </div>
            </div>
            <div class="market">
              <div class="market-title">Over 1.5 filtro: ${escapeHtml(m.over15_filter)}</div>
              <div class="options two">
                ${opt('Over 1.5', m.p_over15)}
                ${opt('Under 1.5', m.p_under15)}
              </div>
            </div>
            <div class="market">
              <div class="market-title">Over / Under 3.5 goles</div>
              <div class="options two">
                ${opt('Over 3.5', m.p_over35)}
                ${opt('Under 3.5', m.p_under35)}
              </div>
            </div>` : ''}
          </div>
          <div class="notes"><b>Riesgo:</b> ${escapeHtml(m.risk)}</div>
          <div class="notes"><b>Argumento:</b> ${escapeHtml(m.argument)}</div>
          <div class="notes">${escapeHtml(m.notes)}</div>
        </article>`;
    }

    function chip(label, value) {
      return `<div class="chip"><strong>${label}</strong><span>${Number(value || 0).toFixed(1)}</span></div>`;
    }

    function opt(label, value) {
      return `<div class="opt"><strong>${label}</strong><span>${pct(value)}</span></div>`;
    }

    function escapeHtml(str) {
      return String(str ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[s]));
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
