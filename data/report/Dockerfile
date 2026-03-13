# check=skip=FromPlatformFlagConstDisallowed

# ---- Stage 1: generate figures (native ARM on Apple Silicon) ----
FROM python:3.12-slim AS figures

RUN pip install --no-cache-dir matplotlib numpy pandas scipy

WORKDIR /build
COPY report/generate_figures.py .
COPY results_clean.csv .

RUN python generate_figures.py --input results_clean.csv --outdir /build/fig

CMD ["sh", "-c", "cp /build/fig/*.png /out/"]

# ---- Stage 2: build PDF (amd64 — pandoc/latex has no ARM image) ----
FROM --platform=linux/amd64 pandoc/latex:latest AS report

# Pin tlmgr to the historic 2025 repo so versions match
RUN tlmgr option repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final \
 && tlmgr install \
      tex-gyre \
      booktabs \
      float \
      caption \
      titlesec \
      adjustbox \
      collectbox \
      enumitem \
      extsizes \
 && tlmgr path add

WORKDIR /data
COPY report/report.md report/tables.lua ./
COPY --from=figures /build/fig/*.png ./

ENTRYPOINT []
CMD ["pandoc", "report.md", "-o", "/out/report.pdf", "--pdf-engine=pdflatex", "--lua-filter=tables.lua"]
