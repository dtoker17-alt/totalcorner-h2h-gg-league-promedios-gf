# Football Real Analytics

Dashboard web para analizar futbol real con datos de Bzzoiro Sports Data.

## Fuente

La app usa exclusivamente BSD v2:

- `/api/v2/events/live/`
- `/api/v2/events/`
- `/api/v2/predictions/`
- `/api/v2/events/{id}/prediction/`
- `/api/v2/events/{id}/odds/comparison/`
- `/api/v2/events/{id}/stats/`
- `/api/v2/events/{id}/metadata/`
- `/api/v2/events/{id}/lineups/`

La API key se lee solo en Netlify Functions mediante `BZZOIRO_API_KEY`; nunca se expone al navegador.

## Desarrollo

```powershell
npm install
netlify dev
```

Configura:

```powershell
$env:BZZOIRO_API_KEY="tu_token"
```

## Deploy

```powershell
netlify env:set BZZOIRO_API_KEY <token>
netlify deploy --prod --dir public --functions netlify/functions
```

## Mercados

El analisis cubre los mercados que BSD entrega para cada evento:

- 1X2
- Over/Under 1.5
- Over/Under 2.5
- Over/Under 3.5
- BTTS
- Doble oportunidad
- Draw no bet
- Corners
- Tarjetas rojas

La recomendacion final combina probabilidad BSD, cuotas reales, edge estimado, estado en vivo, estadisticas, alineaciones y factores contextuales disponibles.

## Motor profesional

El ranking de picks aplica criterios usados en modelos de betting profesionales:

- Probabilidad de mercado sin margen (`no-vig`) calculada desde las mejores cuotas disponibles.
- Probabilidad ajustada = mezcla entre prediccion BSD y senal del mercado.
- `expected_value` = probabilidad ajustada * cuota - 1.
- `edge` = probabilidad ajustada - probabilidad implicita de la cuota.
- `fair_odds` para comparar si la cuota ofrecida esta cara o barata.
- Kelly fraccional y limitado para sugerir stake conservador.
- Penalizaciones por EV negativo, edge bajo, baja profundidad de casas, baja confianza BSD y contradiccion fuerte entre modelo y mercado.

El sistema no considera un pick fuerte solo por probabilidad alta. Debe tener EV positivo, edge razonable, cuota disponible y riesgo controlado.

## Historial y liquidacion

Cada vez que se abre `Analizar` en un partido, la app guarda el snapshot del pick en Netlify Blobs:

- evento
- mercado
- pick
- probabilidad
- cuota
- value / score profesional
- EV
- edge
- Kelly sugerido
- riesgo
- analisis

El boton `Liquidar` consulta de nuevo Bzzoiro por evento y marca cada pick como `WON`, `LOST`, `VOID` o `PENDING`. El dashboard muestra win rate, ganadas, perdidas, pendientes y ROI en unidades.

La liquidacion tambien corre automaticamente:

- Netlify ejecuta `auto-settle` cada 10 minutos.
- La web intenta liquidar en silencio al cargar o actualizar si pasaron 10 minutos desde la ultima revision.
