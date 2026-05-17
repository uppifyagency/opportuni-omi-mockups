# SAGONA — Master Doc per l'API OMI Italia

Riferimento canonico per usare l'API Sagona (prezzi immobiliari OMI / Agenzia delle Entrate) in questo working directory.

**Last verified:** 2026-05-13 (test empirico su Modena F257, vedi §6)
**Provenienza:** questa cartella è stata copiata da
`/Desktop/ARKE SITO/Scraper funzionanti/NUOVA UI/ghost_map_pro Final 7dic JS_PIVA/opportuni-poc/`.
L'originale è intatto.

---

## 1. Cos'è — in 3 frasi

L'Agenzia delle Entrate pubblica semestralmente le quotazioni immobiliari OMI (Osservatorio del Mercato Immobiliare) — un set di prezzi €/m² per zona, comune, tipologia, operazione. La banca dati ufficiale è accessibile via portale web (form + captcha) o file Excel pesanti.

**D. Sagona** (d.sagona.20@gmail.com) ha messo davanti a OMI un'API HTTP REST pulita: [https://3eurotools.it/api-quotazioni-immobiliari-omi](https://3eurotools.it/api-quotazioni-immobiliari-omi). Gratis, no auth, ~20 req/min.

Questa è la nostra fonte di verità per prezzi immobiliari italiani.

---

## 2. Endpoint

```
GET https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca
```

### Parametri

| Nome | Obbligatorio | Default | Esempio | Note |
|------|---|---|---------|------|
| `codice_comune` | **sì** | — | `F257` (Modena), `G273` (Palermo), `C352` (Catanzaro), `H501` (Roma) | Codice catastale Belfiore (4 char), case-sensitive |
| `anno` | no | ultimi dati pubblicati AdE | `2021`, `2015`, `2008` | **Verificato fino al 2005**; senza param ritorna l'ultimo semestre rilasciato |
| `operazione` | no | entrambi | `acquisto` \| `affitto` | Default: ritorna entrambi i prezzi nel JSON |
| `zona_omi` | no | tutte | `B3`, `C9`, `D34` | Filtra a una zona specifica; se omesso ritorna tutte le zone del comune |
| `tipo_immobile` | no | tutti | `abitazioni_civili`, `negozi`, `uffici`, … | Filtra a una tipologia; valori ammessi nella tabella §3.3 |
| `metri_quadri` | no | `1` | `100` | **Influenza l'output**: vedi §2.1 sotto |

### 2.1 Comportamento `metri_quadri` — interpretazione critica

Il parametro `metri_quadri` cambia in modo sottile ma sostanziale il significato dell'output:

- **`metri_quadri=1` (default)** → i campi `prezzo_acquisto_*` sono in **€/m²** (acquisto) o **€/m²/mese** (affitto). È la modalità "OMI puro", utile per analisi statistiche, mappe, ranking zone.
- **`metri_quadri=N`** (es. 100) → i campi `prezzo_acquisto_*` sono **moltiplicati per N**, quindi rappresentano il **valore stimato totale** per un immobile di N m² in quella zona. È la modalità "calculator per investitore".

Esempio confronto stessa query (B3 Palermo, abitazioni_civili, acquisto, 2021):
- `metri_quadri=1`   → `prezzo_acquisto_medio: 1145.0` (€/m²)
- `metri_quadri=100` → `prezzo_acquisto_medio: 114500.0` (€ totale)

⚠️ **Implicazione per validation:** se vedi `prezzo_acquisto_medio > 10000` per `abitazioni_civili`, controlla che non sia un output con `metri_quadri` impostato. Gli asserts di sanity range (`0.5% < yield < 20%`) si basano su €/m².

### 2.2 Esempio di richiesta completa

```text
https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca
    ?codice_comune=G273
    &tipo_immobile=abitazioni_civili
    &metri_quadri=100
    &zona_omi=B3
    &operazione=acquisto
    &anno=2021
```

Output (filtrato a una sola tipologia perché `tipo_immobile` era specifico):

```json
{
  "abitazioni_civili": {
    "stato_di_conservazione_mediano_della_zona": "normale",
    "prezzo_acquisto_min":   94000.0,
    "prezzo_acquisto_max":  135000.0,
    "prezzo_acquisto_medio": 114500.0
  }
}
```

Nota: quando NON si specifica `zona_omi`, l'output è una mappa `{zona: {tipo: {prezzi}}}` (struttura completa, vedi §2.3).

### 2.3 Interpretazione min / max / medio — fondamentale per due diligence

**I prezzi `min` / `max` NON sono gli estremi reali delle compravendite.** Sono i confini di un **range tecnico** che OMI usa per stabilire il valore atteso entro la zona, tenendo conto di **stato di conservazione, posizione interna alla zona, piano**. Servono per posizionare un singolo immobile dentro la fascia di mercato.

- **Estremo basso (`min`)** → immobile in **cattive condizioni**, piano terra, esposizione sfavorevole, da ristrutturare
- **Estremo alto (`max`)** → attico ristrutturato, esposizione sud, finiture premium
- **Medio (`medio`)** → media aritmetica `(min+max)/2`, NON la mediana

**Implicazioni operative per investitore:**
1. Per un AVM (Automated Valuation Model) di un immobile concreto, **non basta il prezzo medio** — serve un'analisi qualitativa per posizionarlo nel range (es. interpolazione manuale o LLM-assisted).
2. **`stato_di_conservazione_mediano_della_zona`** ti dice la mediana della zona (`ottimo` / `normale` / `scadente`). Se la maggior parte degli immobili è in stato `scadente`, anche il `min` è poco riferimento per immobili ben tenuti.
3. Per **screening macro** (CAGR, trend, yield zona), il `prezzo_medio` è il riferimento standard — l'asse temporale lo rende comparable a sé stesso anno su anno.

### 2.4 Response shape (senza filtri tipo_immobile/zona_omi)

### Response shape

```json
{
  "B3": {
    "negozi": {
      "stato_di_conservazione_mediano_della_zona": "normale",
      "prezzo_acquisto_min": 1175.0,
      "prezzo_acquisto_max": 2325.0,
      "prezzo_acquisto_medio": 1750.0,
      "prezzo_affitto_min": 11.6,
      "prezzo_affitto_max": 20.75,
      "prezzo_affitto_medio": 16.2
    },
    "uffici": { ... },
    "magazzini": { ... },
    "abitazioni_signorili": { ... },
    "abitazioni_civili": { ... },
    "abitazioni_di_tipo_economico": { ... },
    "box": { ... },
    "posti_auto_scoperti": { ... }
  },
  "C9": { ... },
  "C10": { ... }
}
```

**Una chiamata = un comune intero, tutte le zone × tutte le tipologie × entrambe le operazioni.** Per Modena F257 = 20 zone × ~10 tipi × 2 operazioni × 3 valori (min/max/medio) = ~1.200 datapoint per chiamata.

Prezzi `prezzo_acquisto_*` sono in **€/m² capitale**. Prezzi `prezzo_affitto_*` sono in **€/m²/mese**.

### 2.5 Snippet ready-to-paste

**Python (stdlib, zero install):**

```python
import json, urllib.parse, urllib.request

url = "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca"
params = {
    "codice_comune": "G273",          # Palermo
    "tipo_immobile": "abitazioni_civili",
    "zona_omi": "B3",
    "operazione": "acquisto",
    "anno": "2021",
    # "metri_quadri": "100",          # opzionale: moltiplica i prezzi
}
qs = urllib.parse.urlencode(params)
with urllib.request.urlopen(f"{url}?{qs}", timeout=30) as r:
    data = json.load(r)
print(data)
# → {"abitazioni_civili": {"stato_di_conservazione_mediano_della_zona": "normale",
#                          "prezzo_acquisto_min": 940.0, ...}}
```

**Python con `requests` (più comodo):**

```python
import requests

url = "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca"
params = {
    "codice_comune": "G273",
    "metri_quadri": 100,
    "operazione": "acquisto",
    "zona_omi": "B22",
    "tipo_immobile": "abitazioni_di_tipo_economico",
}
response = requests.get(url, params=params, timeout=30)
print(response.json())
```

**JavaScript (fetch, browser o Node 18+):**

```javascript
const params = new URLSearchParams({
  codice_comune: "G273",
  metri_quadri: 100,
  operazione: "acquisto",
  zona_omi: "B22",
  tipo_immobile: "abitazioni_di_tipo_economico",
});

const res = await fetch(`https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca?${params}`);
const data = await res.json();
console.log(data);
```

**curl (rapido test da shell):**

```bash
curl -sG "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca" \
  --data-urlencode "codice_comune=G273" \
  --data-urlencode "tipo_immobile=abitazioni_civili" \
  --data-urlencode "zona_omi=B3" \
  --data-urlencode "operazione=acquisto" \
  --data-urlencode "anno=2021" \
  | python3 -m json.tool
```

**Rate-limit safe loop (Python, per backfill multipli)**:

```python
import time
for codice in ["F257", "G273", "H501", "C352"]:
    for anno in [2010, 2014, 2018, 2022, None]:  # None = corrente
        p = {"codice_comune": codice}
        if anno: p["anno"] = anno
        # ... fetch + cache
        time.sleep(3.5)  # rispetta 1 req / 3 sec (con margine)
```

Esempio reale full-fledged: vedi `scripts/sagona-backfill.py` in questa repo — fa caching idempotente, retry, SSL fallback macOS.

---

## 3. Universo dati — cosa puoi chiedere

### 3.1 Comuni (~7.900 codici)

Codice catastale Belfiore. Lista ufficiale ISTAT. Esempi:

| Comune | Codice |
|--------|--------|
| Roma | H501 |
| Milano | F205 |
| Modena | F257 |
| Bologna | A944 |
| Torino | L219 |
| Napoli | F839 |

Per la lista completa, sorgenti:
- `https://www.istat.it/it/archivio/6789` (CSV ISTAT)
- [opentaxes/codici-catastali](https://github.com/opentaxes/codici-catastali) su GitHub

### 3.2 Zone OMI (per comune)

Codifica `<fascia><numero>`:
- **B** = centrale (B1, B2, B3, …)
- **C** = semicentrale
- **D** = periferica
- **E** = suburbana
- **R** = rurale / extraurbana

Modena (F257) corrente ha 20 zone: `B3, C9, C10, C11, D29-D36, E4-E11, R3`.

⚠️ **La nomenclatura zone cambia nel tempo.** Modena 2010 aveva `B2` invece di `B3`. Non sono lo stesso poligono — è una riorganizzazione delle zone OMI. Vedi §7 workaround.

### 3.3 Tipologie immobile — tabella completa con corrispondenza catasto

Valori ammessi per il parametro `tipo_immobile` (Sagona API). Tra parentesi la **categoria catastale ufficiale** italiana — fondamentale per due diligence formale e cross-check con visure.

| `tipo_immobile` (Sagona) | Categoria catasto | Descrizione | Tipica destinazione |
|---|---|---|---|
| `abitazioni_signorili` | **A/1** | Abitazioni di tipo signorile | Residenziale premium |
| `abitazioni_civili` | **A/2** | Abitazioni di tipo civile | Residenziale standard (default headline) |
| `abitazioni_di_tipo_economico` | **A/3 – A/4 – A/5** | Abitazioni economiche, popolari, ultrapopolari | Residenziale entry-level |
| `ville_e_villini` | **A/7, A/8** | Villini, ville | Residenziale indipendente |
| `uffici` | **A/10, B/4** | Uffici e studi privati / uffici pubblici | Terziario |
| `uffici_strutturati` | **A/10** | Uffici con caratteristiche strutturali specifiche | Terziario evoluto |
| `negozi` | **C/1** | Negozi e botteghe | Retail / commerciale |
| `magazzini` | **C/2** | Magazzini e locali di deposito | Logistica leggera |
| `capannoni_tipici` | **C/2** | (overlap C/2, classificazione Sagona separa per uso) | Logistica industriale leggera |
| `laboratori` | **C/3** | Laboratori per arti e mestieri | Artigianale / produttivo |
| `box` | **C/6** | Stalle, scuderie, rimesse, autorimesse | Posto auto coperto privato |
| `autorimesse` | **C/6** | (storica, pre-2010, overlap C/6) | Posto auto coperto |
| `posti_auto_coperti` | **C/6, C/7** | Combinato — Sagona aggrega quando ambiguo | Posto auto |
| `posti_auto_scoperti` | **C/7** | Tettoie chiuse o aperte | Posto auto scoperto |
| `capannoni_industriali` | **D/7** | Fabbricati per uso industriale | Industria pesante |
| `centri_commerciali` | **D/8** | Fabbricati per attività commerciali | Retail su scala |

**Note di interpretazione:**

- **`box` vs `autorimesse` vs `posti_auto_coperti`**: tutti C/6 catastalmente, Sagona li distingue per **uso prevalente** e **dimensione**. Un box è tipicamente privato/singolo, un'autorimessa è condominiale, posti_auto_coperti è il termine moderno.
- **`negozi` (C/1) vs `centri_commerciali` (D/8)**: confine grossolano sulla **scala**. Per investitore retail mid-size, `negozi` è il riferimento.
- **`magazzini` (C/2) vs `capannoni_tipici` (C/2)**: stessa categoria catasto, Sagona separa per **dimensione e uso** (magazzini = logistica leggera, capannoni = produzione/storage scala industriale).
- **Categoria `D` (fabbricati a destinazione speciale)**: stima OMI molto meno granulare — confronto con visure catastali reali consigliato per due-diligence accurata.

**Categorie escluse da Sagona OMI** (per scelta del sistema):
- `A/6` (abitazioni di tipo rurale) — fuori dal mercato urbano OMI
- `A/9` (castelli, palazzi storici) — fuori scope OMI
- `A/11` (alloggi tipici dei luoghi) — fuori scope
- `B/1-3, B/5-8` (collegi, conventi, ospedali, …) — uso pubblico/non-commerciale
- `C/4, C/5` (cinema, stabilimenti balneari) — out of scope per OMI standard
- `D/1, D/2, D/3, D/4, D/5, D/6, D/9, D/10` (banche, alberghi, teatri, ospedali privati, … e fabbricati rurali) — alcune in OMI separato, non sempre via Sagona

**Cross-reference con Anagrafe Catastale Agenzia delle Entrate:**
- Tabella ufficiale categorie: https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/categorie-catastali
- Una visura catastale di un immobile riporta la categoria esatta (es. `A/2`), che permette di mapparla 1-to-1 con la `tipo_immobile` Sagona corrispondente per il lookup di valore di mercato.

**Per applicazioni investitore — quale tipologia interrogare:**

| Tipo di investitore | Tipologia da privilegiare |
|---|---|
| Compravendita residenziale standard | `abitazioni_civili` (A/2) |
| Residenziale premium / luxury | `abitazioni_signorili` (A/1) + `ville_e_villini` |
| Buy-to-let entry / yield play | `abitazioni_di_tipo_economico` (A/3-4-5) |
| Commerciale retail | `negozi` (C/1) |
| Terziario uffici | `uffici` (A/10, B/4) |
| Logistica leggera / e-commerce last-mile | `magazzini` (C/2) |
| Industriale | `capannoni_industriali` (D/7) |
| Retail park / mall investor | `centri_commerciali` (D/8) |
| Box-investing (asset class minore ma con yield interessanti in centro città) | `box` (C/6) |
| Posti auto in zone turistiche / stazioni | `posti_auto_scoperti` (C/7) |

### 3.4 Range temporale

**Verificato empiricamente fino al 2005** (Modena, 2026-05-13). OMI pubblica dal 2007 ufficialmente — Sagona arriva al 2005, quindi include i dati ante-riforma.

Frequenza ufficiale: semestrale (gennaio + luglio).

→ **20 anni × 2 semestri = ~40 datapoint temporali per zona × tipologia × operazione**.

---

## 4. Comandi pratici — copia-incolla

### 4.1 Snapshot attuale di un comune
```bash
curl -s "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca?codice_comune=F257" \
  | python3 -m json.tool > modena-attuale.json
```

### 4.2 Backfill storico — un anno
```bash
curl -s "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca?codice_comune=F257&anno=2010" \
  | python3 -m json.tool > modena-2010.json
```

### 4.3 Solo negozi in affitto, zona B3
```bash
curl -s "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca?codice_comune=F257&zona_omi=B3&tipo_immobile=negozi&operazione=affitto"
```

### 4.4 Backfill loop 2005→oggi per Modena (bash one-liner)
```bash
for anno in 2005 2008 2010 2012 2015 2018 2020 2022 2024; do
  echo "=== $anno ==="
  curl -s "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca?codice_comune=F257&anno=$anno" \
    > "modena-$anno.json"
  sleep 4   # rispetta rate limit
done
```

### 4.5 Estrai serie temporale di una zona (es. centro Modena, negozi acquisto)
```bash
for f in modena-*.json; do
  anno="${f#modena-}"; anno="${anno%.json}"
  prezzo=$(python3 -c "
import json
d = json.load(open('$f'))
# cerca prima la zona che ha 'negozi' più centrale (B-fascia)
for z in sorted(d.keys()):
    if z.startswith('B') and 'negozi' in d[z]:
        print(d[z]['negozi'].get('prezzo_acquisto_medio', ''))
        break
")
  echo "$anno,$prezzo"
done > modena-negozi-centro-serie.csv
```

### 4.6 ETL Python integrato (già in questa repo)
```bash
cd opportuni-poc
.venv/bin/python etl/sagona_prezzi.py        # 3 comuni hardcoded (Milano/Torino/Bologna)
```
Va modificato per Modena — vedi §8.

---

## 5. Rate limit + workarounds

### Dichiarazione ufficiale Sagona
- 100 req crediti iniziali
- Ricarica: 1 req ogni 3 secondi
- **Niente API key, niente auth**
- Headers utili: `User-Agent` rispettoso, `Referer` non richiesto

### Workaround #1 — Cache aggressiva con chiave temporale
L'ETL attuale ([etl/sagona_prezzi.py:46](etl/sagona_prezzi.py#L46)) cachea `data/cache/sagona/{codice}.json`. **Bug:** sovrascrive il backfill. Fix:
```python
cache_path = CACHE_DIR / f"{codice}_{anno or 'current'}.json"
```

### Workaround #2 — Loop con pausa rispettosa
```python
import time
DELAY = 3.5  # >= 3.0 per stare sotto al limite
for codice in comuni_lista:
    for anno in anni_lista:
        fetch_comune(codice, anno=anno)
        time.sleep(DELAY)
```

A 3.5 s/req:
- 1 comune × 20 anni = ~70 secondi
- 47 comuni provincia Modena × 20 anni = ~55 minuti
- ~7.900 comuni Italia × 20 anni = **~9,2 giorni** wall-clock una tantum
- ~7.900 comuni Italia × 1 anno (refresh semestrale) = ~7,7 ore

### Workaround #3 — Parallelismo con proxy SOCKS5
business-finder ha già `--proxy socks5://...` con pool. Stesso schema: distribuire le richieste su N proxy con limit per-host.
- 3 proxy in parallelo = ~3 giorni invece di 9
- ⚠️ Cortesia: l'API è di una persona singola, non massacrarla.

### Workaround #4 — Cache distribuita
Se più di un progetto usa Sagona, mettere una cache shared (Postgres / S3) per evitare ri-fetch.

### Workaround #5 — Fallback su sorgenti ufficiali
Se Sagona scompare (rischio bus-factor: un singolo dev), fallback:
- File Excel ufficiali OMI: [agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi](https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi)
- Repository GitHub con parser OMI: cerca `omi italia quotazioni` su github
- onData APS: [https://www.ondata.it/i-dati-sulle-quotazioni-immobiliari-dellagenzia-entrate-i-poligoni-delle-zone-omi/](https://www.ondata.it/i-dati-sulle-quotazioni-immobiliari-dellagenzia-entrate-i-poligoni-delle-zone-omi/)

---

## 6. Test empirico Modena — 2026-05-13

Verifica diretta che faccio prima di committermi al test Modena.

```
F257 (Modena) — corrente
  zone = 20
  codici = B3, C9, C10, C11, D29-D36, E4-E11, R3
  esempio negozi zona B3:
    acquisto min/medio/max = 1175 / 1750 / 2325 €/m²
    affitto min/medio/max  = 11.6 / 16.2 / 20.75 €/m²/mese

F257 (Modena) — anno=2015
  ✅ dati pieni
  esempio negozi zona B3:
    acquisto medio = 2562.5 €/m²  ← significativamente più alto del 2026

F257 (Modena) — anno=2010
  ✅ dati pieni
  esempio negozi zona B2 (renomenclatura):
    acquisto medio = 4500 €/m²

F257 (Modena) — anno=2005
  ✅ dati pieni
  esempio negozi zona B2:
    acquisto medio = 5000 €/m²
  presenti categorie extra: autorimesse
```

**Trend chiaro:** prezzi negozi centro Modena 2005=5000 → 2010=4500 → 2015=2562 → 2026=1750 €/m². Calo del 65% in 20 anni. La crisi post-2008 + de-popolazione centri storici emerge a colpo d'occhio.

---

## 7. Idiosincrasie scoperte

### 7.1 Renomenclatura zone nel tempo
Modena 2010 = `B2`, Modena 2015+ = `B3`. Non sono lo stesso poligono. Per le serie temporali:
- **Approccio "fascia"**: aggrega su fascia (B/C/D/E/R) — sopravvive ai renaming
- **Approccio "geometria"**: se hai i poligoni, fai spatial join e mappi `B2_2010 → B3_2026` se sovrappongono >70%
- **Approccio "manuale"**: tabella di mapping curata zona × anno → zona_canonica

### 7.2 Categorie variabili
`autorimesse` esiste nel 2005 ma è probabilmente sparita / unita a `box` in epoche successive. Per serie consistenti, normalizzare con mapping:
- `autorimesse` → `box` (fallback storico)
- nessuna categoria 2026 introvabile nel 2005

### 7.3 `metri_quadri=1` di default
Significa che i totali calcolati (es. €/m² × m²) sono sempre €/m². Setterlo solo se vuoi euro assoluti.

### 7.4 Cache della cache
Sagona è già un wrapper. Se OMI ufficiale aggiorna ma Sagona non rifetcha, c'è lag. Frequenza Sagona non documentata — assumi aggiornamento entro 1-2 mesi dalla pubblicazione OMI ufficiale.

---

## 8. Cosa devi cambiare per usarlo da qui

### 8.1 Aggiungere Modena al PoC esistente
Modifica [etl/sagona_prezzi.py:37](etl/sagona_prezzi.py#L37):
```python
COMUNI = {
    "F205": "Milano",
    "L219": "Torino",
    "A944": "Bologna",
    "F257": "Modena",            # <-- aggiungi
}
```

### 8.2 Estendere ETL al backfill storico
Aggiungere parametro `anno` al fetch:
```python
def fetch_comune(base_url, codice, *, anno=None, force=False):
    suffix = f"_{anno}" if anno else "_current"
    cache_path = CACHE_DIR / f"{codice}{suffix}.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text())
    params = {"codice_comune": codice}
    if anno:
        params["anno"] = anno
    resp = requests.get(base_url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache_path.write_text(json.dumps(data))
    return data

def main_backfill():
    for codice in COMUNI:
        for anno in [2005, 2008, 2010, 2012, 2015, 2018, 2020, 2022, 2024, None]:
            response = fetch_comune(base_url, codice, anno=anno)
            rilevazione_at = datetime(anno or current_year, 1, 1, tzinfo=timezone.utc)
            rows = parse_response_to_rows(codice, response, rilevazione_at)
            upsert_prezzi(rows)
            time.sleep(DELAY)
```

### 8.3 Recuperare poligoni Modena
**Approccio A — GeoPOI reverse-engineered (AUTOMATICO, scoperto 2026-05-13):**

Lo script [scripts/geopoi-zone-extract.py](scripts/geopoi-zone-extract.py) chiama 2 endpoint interni:

```
GET https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/zoneomi.php?richiesta=3&codcom=<X>
    → JSON {LINK_ZONA, FASCIA, ZONA, DIZIONE} per ogni zona OMI del comune

GET https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/perimetri.php?id=1&prov=<P>&codcom=<X>&semestre=<YYYYS>&formato=kml
    → KMZ (zip di KML) con i poligoni — semestre in formato compatto: 20241, NON 2024/1
```

Usage:
```bash
python3 scripts/geopoi-zone-extract.py \
  --codcom F257 --prov MO --semestre 20241 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/modena-zone-omi.geojson
```

Output: GeoJSON con 19 poligoni Modena, ogni feature ha `zona`, `fascia`, `dizione` ("CAPOLUOGO - CENTRO STORICO"), `link_zona`, e tutti i prezzi correnti per tipo immobile (joinati da `sagona-backfill/prezzi.csv`).

**Approccio B — GeoPOI portale manuale (fallback):**
1. Vai a [www1.agenziaentrate.gov.it/servizi/geopoi_omi/index.php](https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/index.php)
2. Seleziona provincia, scarica KMZ
3. Converti con `ogr2ogr -f GeoJSON modena_zone.geojson modena_zone.kml`

**Approccio B — dati.gov.it (vale la pena cercare):**
- Listing su [dati.gov.it/node/192?tags=zone-omi](https://www.dati.gov.it/node/192?tags=zone-omi)

**Approccio C — Comune di Modena open data:**
- Catalogo: [opendata.comune.modena.it](https://opendata.comune.modena.it/catalog.rdf)
- ⚠️ Hanno "quartieri", non zone OMI — diversi

**Approccio D — Provincia di Modena cartografia:**
- [www.provincia.modena.it/temi-e-funzioni/territorio/.../elaborati-cartografici-in-formato-shape-file/](https://www.provincia.modena.it/temi-e-funzioni/territorio/pianificazione-territoriale-e-difesa-del-suolo/p-t-c-p/p-t-c-p-approvato/elaborati-cartografici-in-formato-shape-file/) — shapefile pianificazione (non OMI)

→ Approccio A è la fonte autoritativa.

---

## 9. Integrazione con Printing Press (la nostra strategia)

Sagona è il caso d'uso perfetto per il `printing-press --docs`:

```bash
cd ../cli-printing-press
../bin/printing-press generate \
  --docs https://3eurotools.it/api-quotazioni-immobiliari-omi \
  --spec-extension '{"x-pp-cache":{"sqlite":true,"key":"codice_comune,anno"}}' \
  --out  ../out/sagona-omi-pp-cli
```

Output atteso:
- `sagona-omi-pp-cli quotazioni --codice-comune F257 [--anno 2010]` → JSON pulito
- `sagona-omi-pp-cli backfill --codice-comune F257 --from 2005 --to 2026` → loop con rate limit interno
- `sagona-omi-pp-cli series --codice-comune F257 --tipo negozi --zona-fascia B` → serie temporale CSV
- Cache SQLite locale → no re-fetch
- MCP server → Claude lo chiama nativamente
- SKILL.md → "quanto costavano i negozi a Modena centro nel 2010?" → query naturale

**Questo CLI sostituirebbe `etl/sagona_prezzi.py`** rendendolo riusabile da chiunque, non vincolato a opportuni-poc.

---

## 10. Roadmap per "usare al massimo Sagona"

### Tier 1 — Test PoC Modena (1 giorno)
- [ ] Aggiungere F257 a COMUNI nel ETL
- [ ] Backfill Modena dal 2005 (20 anni × 1 chiamata = ~1 min)
- [ ] Scaricare poligoni Modena GML → GeoJSON
- [ ] Generare grafico HTML evoluzione prezzi Modena centro
- [ ] Generare mappa choropleth zone Modena oggi

### Tier 2 — Provincia di Modena (~1 giorno)
- [ ] Lista 47 comuni provincia Modena (CSV da ISTAT)
- [ ] Backfill provincia: 47 × 10 anni × 3.5s = ~55 min
- [ ] Dashboard drill-down: selettore comune → serie temporale

### Tier 3 — Italia × Tempo (1-2 settimane wall-clock)
- [ ] Lista 7.900 comuni ISTAT
- [ ] Backfill snapshot 2005-2026: 9,2 giorni (single proxy) o 3 giorni (3 proxy)
- [ ] Schema partizione TimescaleDB già pronta (90gg chunk)
- [ ] Refresh semestrale auto (cron gennaio + luglio)

### Tier 4 — Stampare il CLI Sagona universale
- [ ] Generate con Printing Press
- [ ] Pubblicare su `~/printing-press/library/sagona-omi/`
- [ ] MCP integration: chiunque con Claude Code può "quanto costa la casa a Modena nel 2015"

### Tier 5 — Cross-pollination con business-finder
- [ ] In business-finder, aggiungere `--enrich-omi` che chiama sagona-omi-pp-cli per ogni business trovato
- [ ] Output: lista business + zona OMI in cui si trovano + prezzo medio di affitto attuale e storico
- [ ] Use case: "in che zona OMI sta il mio cliente, quanto paga di affitto rispetto alla mediana?"

---

## 11. File chiave in questa cartella

| File | Cosa fa | Quando leggerlo |
|------|---------|----|
| [README.md](README.md) | Setup rapido del PoC | Quando vuoi farlo girare in locale |
| [DECISION_MEMO.md](DECISION_MEMO.md) | Decision log del run originale (2026-05-04, 50 min autonomo) | Per capire il razionale architetturale |
| [STATUS.md](STATUS.md) | Iteration log del loop autonomo | Per capire come è stato costruito |
| [migrations/001_init.sql](migrations/001_init.sql) | Schema DB completo (9 tabelle, 2 hypertable) | Prima di toccare il DB |
| [etl/sagona_prezzi.py](etl/sagona_prezzi.py) | Wrapper Python per Sagona | Per estendere a Modena / backfill |
| [etl/milano_zone_omi.py](etl/milano_zone_omi.py) | Loader poligoni zone Milano (CKAN) | Per replicare il pattern su Modena |
| [worker/](worker/) | Cloudflare Worker per `/api/sync` (Ghost Map → DB) | Solo se mantieni l'integrazione GMP |
| [dashboard/](dashboard/) | Next.js 15 + MapLibre choropleth | Da estendere per il test Modena |
| [docker-compose.yml](docker-compose.yml) | Postgres 16 + PostGIS + TimescaleDB | Per setup locale |
| [Makefile](Makefile) | `make up && make migrate && make demo` | Demo runnable in un colpo |

---

## 12. Riferimenti esterni

- **Sagona API** — [https://3eurotools.it/api-quotazioni-immobiliari-omi](https://3eurotools.it/api-quotazioni-immobiliari-omi) (autore D. Sagona, d.sagona.20@gmail.com)
- **GeoPOI ufficiale Agenzia Entrate** — [https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/](https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/)
- **Banche dati OMI ufficiali (Excel)** — [https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi](https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi)
- **onData APS — articolo poligoni OMI** — [https://www.ondata.it/i-dati-sulle-quotazioni-immobiliari-dellagenzia-entrate-i-poligoni-delle-zone-omi/](https://www.ondata.it/i-dati-sulle-quotazioni-immobiliari-dellagenzia-entrate-i-poligoni-delle-zone-omi/)
- **dati.gov.it tag zone-omi** — [https://www.dati.gov.it/node/192?tags=zone-omi](https://www.dati.gov.it/node/192?tags=zone-omi)
- **CKAN Milano dataset** (utilizzato dal PoC) — [https://dati.comune.milano.it/dataset/e951b95a-5923-4a01-add1-e01e72ffda8a](https://dati.comune.milano.it/dataset/e951b95a-5923-4a01-add1-e01e72ffda8a)
- **ISTAT codici catastali** — [https://www.istat.it/it/archivio/6789](https://www.istat.it/it/archivio/6789)

---

## 13. Note legali

- Sagona dichiara "free for commercial use", **attribuzione richiesta** per progetti pubblici → cita "D. Sagona / 3eurotools.it" e "Agenzia delle Entrate — OMI" nei tuoi output.
- OMI è dato pubblico ufficiale (Agenzia delle Entrate, ente pubblico).
- Per launch commerciale serio (es. SaaS che monetizza i dati OMI), il PoC originale stimava **€4-8k legal opinion specializzato (1-3 mesi)**. Vedi [DECISION_MEMO.md:88-91](DECISION_MEMO.md#L88).
- Rate limit: rispettarlo è anche etica. Non massacrare il servizio di un singolo dev.
