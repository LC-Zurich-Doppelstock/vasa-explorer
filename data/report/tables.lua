-- Lua filter: convert pandoc tables to raw LaTeX tabular (no longtable)
-- so they work inside twocolumn mode. Renders captions via \captionof{table}.

local function escape_latex(s)
  s = s:gsub("\\", "\\textbackslash{}")
  s = s:gsub("([#$%%&_{}])", "\\%1")
  s = s:gsub("~", "\\textasciitilde{}")
  s = s:gsub("%^", "\\textasciicircum{}")
  s = s:gsub("%-%-%-", "\\textemdash{}")
  s = s:gsub("%-%-", "\\textendash{}")
  return s
end

function Table(tbl)
  local ncols = #tbl.colspecs
  local aligns = {}
  for i, colspec in ipairs(tbl.colspecs) do
    local a = colspec[1]
    if a == pandoc.AlignLeft or a == pandoc.AlignDefault then
      aligns[#aligns+1] = "l"
    elseif a == pandoc.AlignRight then
      aligns[#aligns+1] = "r"
    elseif a == pandoc.AlignCenter then
      aligns[#aligns+1] = "c"
    else
      aligns[#aligns+1] = "l"
    end
  end

  local colspec_str = table.concat(aligns, " ")

  local function render_row(row)
    local cells = {}
    for _, cell in ipairs(row.cells) do
      local content = escape_latex(pandoc.utils.stringify(cell.contents))
      cells[#cells+1] = content
    end
    return table.concat(cells, " & ") .. " \\\\"
  end

  -- Extract caption if present
  local caption_text = nil
  if tbl.caption and tbl.caption.long and #tbl.caption.long > 0 then
    caption_text = pandoc.utils.stringify(tbl.caption.long)
  end

  local lines = {}
  lines[#lines+1] = "\\begin{center}"
  lines[#lines+1] = "\\small"
  lines[#lines+1] = "\\begin{tabular}{" .. colspec_str .. "}"
  lines[#lines+1] = "\\toprule"

  -- Header
  if tbl.head and tbl.head.rows then
    for _, row in ipairs(tbl.head.rows) do
      lines[#lines+1] = render_row(row)
    end
  end
  lines[#lines+1] = "\\midrule"

  -- Body
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      lines[#lines+1] = render_row(row)
    end
  end

  lines[#lines+1] = "\\bottomrule"
  lines[#lines+1] = "\\end{tabular}"

  -- Caption below the table (uses \captionof from caption package)
  -- pandoc-crossref prepends "Table N: " to the caption; strip it so
  -- \captionof can generate its own numbering consistently.
  local tbl_id = tbl.attr and tbl.attr.identifier or ""
  if caption_text and caption_text ~= "" then
    caption_text = caption_text:gsub("^Table%s+%d+:%s*", "")
    local label = ""
    if tbl_id ~= "" then
      label = "\\label{" .. tbl_id .. "}"
    end
    lines[#lines+1] = "\\captionof{table}{" .. escape_latex(caption_text) .. "}" .. label
  elseif tbl_id ~= "" then
    lines[#lines+1] = "\\label{" .. tbl_id .. "}"
  end

  lines[#lines+1] = "\\end{center}"

  return pandoc.RawBlock("latex", table.concat(lines, "\n"))
end
