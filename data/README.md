# Vasaloppet Data & Report

Race results and analysis report for 15 editions of the 90 km Vasaloppet
(2011--2026, excluding the 2021 COVID elite-only edition).

## Structure

| Path | Purpose |
|------|---------|
| `results_clean.csv` | Cleaned race results (238k rows) |
| `scrape_vasaloppet.py` | Scraper for vasaloppet.se results |
| `report/report.md` | Report source (Pandoc Markdown with LaTeX front matter) |
| `report/generate_figures.py` | Reads `results_clean.csv`, writes 6 analysis PNGs |
| `report/tables.lua` | Pandoc Lua filter for twocolumn-safe table rendering |
| `report/Dockerfile` | Multi-stage build definition |
| `report/figs/` | Generated analysis figures (output) |

## Building the report

A two-stage Docker build generates analysis figures and compiles the PDF.

| Stage | Base image | What it does |
|-------|-----------|--------------|
| `figures` | `python:3.12-slim` (native) | Runs `generate_figures.py` against `results_clean.csv` to produce 6 PNG figures |
| `report` | `pandoc/latex` (amd64) | Copies figures from stage 1, runs Pandoc with pdflatex to produce `report.pdf` |

The `pandoc/latex` image only ships amd64, so stage 2 runs under QEMU on
Apple Silicon. Stage 1 runs natively to keep figure generation fast.

All commands run from this directory.

```bash
# Generate figures only (native, fast)
docker build -t pandoc-figures --target figures -f report/Dockerfile .
docker run --rm -v "$(pwd)/report/figs":/out pandoc-figures

# Generate figures + PDF (builds both stages, then runs pandoc)
docker build -t pandoc-report -f report/Dockerfile .
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/report":/out \
  pandoc-report
```

Outputs:
- `report/report.pdf` -- the compiled report
- `report/figs/*.png` -- the 6 analysis figures
