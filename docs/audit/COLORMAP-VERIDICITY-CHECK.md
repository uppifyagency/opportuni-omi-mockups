# Audit veridicità cromatica — colori delle mappe vs segno del CAGR

**Data:** 2026-05-17
**Esito globale:** 0 falsificazioni cromatiche su 318 entry totali

## Invarianti testate
- CAGR > +0.2%/yr → colore deve essere VERDE (G > R)
- CAGR < −0.2%/yr → colore deve essere ROSSO (R > G)
- |CAGR| ≤ 0.2%/yr → colore beige (R≈G entrambi alti)

## Risultati per città × scope

| Città | Scope | N | P5 clamp | P95 clamp | Falsificazioni |
|---|---|---:|---:|---:|---:|
| **modena** | zone | 20 | -0.50 | +0.74 | ✅ 0 |
| **modena** | provincia | 47 | -0.01 | +0.76 | ✅ 0 |
| **bologna** | zone | 31 | -0.12 | +0.58 | ✅ 0 |
| **bologna** | provincia | 55 | -0.27 | +0.65 | ✅ 0 |
| **catanzaro** | zone | 19 | -0.50 | +0.91 | ✅ 0 |
| **catanzaro** | provincia | 80 | -0.50 | +2.86 | ✅ 0 |
| **reggio-emilia** | zone | 24 | -0.50 | +2.15 | ✅ 0 |
| **reggio-emilia** | provincia | 42 | -0.89 | +0.50 | ✅ 0 |