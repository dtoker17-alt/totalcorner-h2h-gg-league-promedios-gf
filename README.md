# H2H GG League eSoccer Bot

Sistema local para revisar eSoccer H2H GG League cada 10 minutos, enviar las mejores jugadas por Telegram, guardar picks en Excel y resolver resultados para medir rendimiento.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con tu `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.

## Uso

Una corrida:

```powershell
python -m h2hbot run-once
```

Modo continuo cada 10 minutos:

```powershell
python -m h2hbot loop
```

Tambien puedes usar:

```powershell
.\scripts\run_loop.ps1
```

O instalarlo en el Programador de tareas de Windows:

```powershell
.\scripts\install_task.ps1
```

Solo resolver picks pendientes:

```powershell
python -m h2hbot settle
```

Resumen de rendimiento:

```powershell
python -m h2hbot report
```

Entrenamiento autonomo de picks fuertes:

```powershell
python -m h2hbot train
.\scripts\train_loop.ps1
```

Esto registra picks fuertes en `data/picks_history.xlsx`, hoja `Training`, y liquida ganadas/perdidas cuando TotalCorner marca el partido como `Full`.

App web local para celular:

```powershell
python -m h2hbot.webapp --host 0.0.0.0 --port 8000
```

O:

```powershell
.\scripts\start_webapp.ps1
```

Abre en la PC `http://localhost:8000`. Para verlo en celular, conecta el celular a la misma red Wi-Fi y abre `http://IP-DE-TU-PC:8000`.

## Odds manuales de Codere

Si quieres medir value real, llena `data/odds.csv` con:

```csv
match_time,home,away,market,line,odds
2026-06-08 10:08,LAVA,DEZZY,over_goals,2.5,1.90
```

Sin odds, el bot aun manda picks por probabilidad estimada, pero marca `edge` como pendiente.

## Excel

El historial se guarda en `data/picks_history.xlsx` con:

- picks enviados
- resultado final cuando se encuentra
- win/loss/push
- odds, edge y profit estimado cuando hay cuota
- resumen acumulado

## Notas

Las fuentes web de eSoccer cambian con frecuencia. Los URLs estan en `.env` para poder ajustarlos sin tocar codigo.
