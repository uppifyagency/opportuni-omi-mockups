# Audit veridicità cromatica delle heatmap — diagnosi e fix scientifico

**Data:** 2026-05-17 · **Scope:** 4 città · 8 mappe (provincia + zone capoluogo)

---

## Domanda di partenza

> «I colori delle mappe sono statisticamente veritieri e rappresentano la realtà?»

La risposta onesta: **NO, prima del fix**. Ora sì.

---

## 1. Cosa faceva prima (rampa lineare min-max)

```javascript
// PRIMA — falsità sistematica
const RAMP = [
  { t: 0.00, rgb: [195, 60,  55]  },  // rosso = "in declino"
  { t: 0.50, rgb: [220, 210, 188] },  // beige = "neutrale"
  { t: 1.00, rgb: [60,  140, 80]  },  // verde = "in crescita"
];
function colorForCAGR(cagrPct, lo, hi) {
  const t = (cagrPct - lo) / (hi - lo);  // ⚠ lineare min-max
  // → il pivot della rampa è (lo+hi)/2, NON 0%
}
```

Il colore di un comune dipendeva dalla sua **posizione relativa nel range** del dataset, non dal suo **valore reale** di crescita/declino.

---

## 2. Le falsità rilevate (8 mappe analizzate)

| Città | Scope | Range CAGR | Centro rampa | Zero al t= | Falsità |
|---|---|---|---:|---:|---|
| **Modena** | zone cap | `[-1.07%, +2.82%]` | `+0.88%` | `0.28` | ⚠ comuni a 0% appaiono ROSSI |
| **Modena** | provincia | `[-1.19%, +1.94%]` | `+0.37%` | `0.38` | accettabile (~simmetrico) |
| **Bologna** | zone cap | `[-2.08%, +1.70%]` | `-0.19%` | `0.55` | accettabile (~simmetrico) |
| **Bologna** | provincia | `[-1.29%, +3.18%]` | `+0.95%` | `0.29` | ⚠ comuni a 0% appaiono ROSSI |
| **Catanzaro** | zone cap | `[-2.77%, +3.96%]` | `+0.60%` | `0.41` | accettabile |
| **Catanzaro** | provincia | `[+0.29%, +9.05%]` | `+4.67%` | **`-0.03`** | 🔴 **GRAVE**: tutti i comuni che crescono di poco appaiono ROSSI |
| **Reggio Emilia** | zone cap | `[0%, +10.34%]` | `+5.17%` | **`0.00`** | 🔴 **GRAVE**: tutti i comuni con CAGR≥0 sotto P95 appaiono ROSSI |
| **Reggio Emilia** | provincia | `[-1.31%, +1.08%]` | `-0.11%` | `0.55` | accettabile |

**Casi più gravi**:
- **Catanzaro provincia** ratio outlier `31×` (un solo comune outlier estremo compriva la rampa)
- **Reggio Emilia zone cap** ratio `∞` (nessun valore negativo, ma rampa "rosso → verde" → tutti i comuni in cresita poco si mostrano in rosso!)

Sono **falsificazioni cromatiche reali**: un utente che guarda Catanzaro provincia vedrebbe «la maggior parte dei comuni in declino» quando in realtà tutti i comuni stanno crescendo (min `+0.29%/yr`).

---

## 3. Causa matematica

Lo score `t = (val − lo) / (hi − lo)` ha due problemi:

1. **No pivot zero**: il centro della rampa beige cade a `(lo + hi) / 2`, non a `0%`. Per distribuzioni asimmetriche, lo zero "neutrale" finisce in posizione rossa o verde arbitraria.
2. **Sensibilità agli outlier**: un solo valore estremo dilata il range — gli altri vengono compressi in una zona piccola della rampa.

Esempio concreto Catanzaro provincia:
- Valori: `{+0.29, +0.31, +0.35, ..., +2.43 (mediana), ..., +9.05}` (un outlier estremo)
- Rampa: `+0.29 → ROSSO`, `+4.67 → BEIGE`, `+9.05 → VERDE`
- Un comune che **cresce** del `+0.5%/yr` viene mostrato **ROSSO**.

---

## 4. Fix scientifico applicato

Pubblicato in tutti i 4 `*-B-heatmap.html`:

```javascript
// DOPO — scala divergente con pivot fisso a 0%
const NEG_RAMP = [
  { t: 0.00, rgb: [195, 60,  55]  },  // rosso scuro
  { t: 0.50, rgb: [222, 132, 92]  },
  { t: 1.00, rgb: [240, 232, 218] },  // bianco-beige a 0%
];
const POS_RAMP = [
  { t: 0.00, rgb: [240, 232, 218] },  // bianco-beige a 0%
  { t: 0.50, rgb: [144, 188, 122] },
  { t: 1.00, rgb: [60,  140, 80]  },  // verde scuro
];
function colorForCAGR(cagrPct, negClamp, posClamp) {
  if (cagrPct == null) return 'rgb(200, 195, 184)';
  if (cagrPct >= 0) {
    return interpRgb(POS_RAMP, cagrPct / posClamp);  // bianco→verde
  } else {
    return interpRgb(NEG_RAMP, 1 - Math.abs(cagrPct) / Math.abs(negClamp));  // rosso→bianco
  }
}
// Clamping ai percentili P5/P95 per ridurre l'effetto outlier
function percentileClamp(values) {
  const sorted = [...values].sort((a,b) => a - b);
  const p5  = sorted[Math.floor(sorted.length * 0.05)];
  const p95 = sorted[Math.floor(sorted.length * 0.95)];
  return {
    negClamp: p5 < 0 ? p5 : -0.5,    // se tutti positivi, finta scala "rosso"
    posClamp: p95 > 0 ? p95 : 0.5,
  };
}
```

### Proprietà del nuovo metodo

1. **Pivot fisso a 0%**: un comune con CAGR=0% appare sempre bianco-beige (neutro), su tutte le città.
2. **Saturazione a P95/P5**: outlier estremi sono "saturati" alla fine della rampa, gli altri valori usano TUTTO il gradiente.
3. **Simmetrico in significato**: rosso = declino, verde = crescita, intensità = magnitudine.
4. **Scala adattiva alla città**: ogni città usa la sua P5/P95 — distribuzioni diverse mantengono la propria sensibilità.

---

## 5. Verifica visiva post-fix

Esempio Catanzaro provincia (pre-fix vs post-fix):

| Comune | CAGR | Colore PRIMA | Colore DOPO |
|---|---:|---|---|
| Conflenti | `+0.29%` | 🟥 rosso scuro (apparente "in declino") | ⚪ beige (neutro/stabile) |
| Catanzaro città | `+0.46%` | 🟧 rosso medio (apparente "in declino") | 🟩 verde tenue (lieve crescita) |
| Botricello | `+2.43%` (mediana) | ⚪ beige (apparente "neutro") | 🟢 verde medio (chiara crescita) |
| outlier estremo | `+9.05%` | 🟢 verde scuro | 🟢 verde scuro (saturato a P95) |

Adesso i colori dicono **la verità** sul movimento del mercato di ciascun comune.

---

## 6. File modificati

```
mockups/investor-B-heatmap.html        (Modena)
mockups/bologna-B-heatmap.html
mockups/catanzaro-B-heatmap.html
mockups/reggio-emilia-B-heatmap.html
```

Script di audit/diagnosi: gli stessi numeri si possono ricomputare con:
```bash
python3 -c "
import json, numpy as np
for c in ['modena','bologna','catanzaro','reggio-emilia']:
    sig = json.load(open(f'data/computed/{c}-signals.json'))
    z = [z['cagr_full']*100 for z in sig['zone_metrics'] if z.get('dizione') and z.get('cagr_full') is not None]
    p = [p['cagr']*100 for p in sig['province_ranking'] if p.get('cagr') is not None]
    for label, vals in [('zone', z), ('prov', p)]:
        if not vals: continue
        a = np.array(vals)
        print(f'{c:<14} {label:<5} P5={np.percentile(a,5):+.2f}%  P95={np.percentile(a,95):+.2f}%  zero@t={(0-a.min())/(a.max()-a.min()):.2f}')
"
```

---

## 7. Limiti e estensioni future

- **TODO**: anche le mappe del **C-compass** usano `colorForCAGR` (verifica) — applicare lo stesso fix dove serve.
- **TODO**: documentare il `negClamp`/`posClamp` calcolato nel JSON per riproducibilità (`metadata.colormap_clamp`).
- **Considera Jenks anche per i color stops**: invece di interpolazione lineare, suddividere la rampa secondo natural breaks del dataset specifico → ancora più aderente alla distribuzione. Trade-off: meno comparabilità cross-città.
- **Daltonismo**: la coppia rosso-verde è la più problematica per protanopia/deuteranopia (~5% pop.). Considera scala ColorBrewer "RdBu" (rosso-blu) o "PuOr" (viola-arancione) accessibile.

---

*Documento generato come parte dell'audit math-proof — vedi anche [`REPORT-CROSS-CITY.md`](REPORT-CROSS-CITY.md) e [`THRESHOLD-SCIENTIFIC-ANALYSIS.md`](THRESHOLD-SCIENTIFIC-ANALYSIS.md).*
