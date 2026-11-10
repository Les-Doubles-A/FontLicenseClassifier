"""
Generation des rapports finaux : rapport.csv, rapport.xlsx, rapport.html
(point 6 du cahier des charges). Chaque ligne contient : nom du fichier,
nom de la police, designer, version, licence detectee, source de la
detection, URL, score de confiance et date d'analyse.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from license_detector.models import ClassificationResult
from scanner.font_scanner import FontInfo

logger = logging.getLogger("fontlicense.reports")

COLUMNS = [
    "Fichier", "Nom de la police", "Nom complet", "Designer", "Editeur",
    "Version", "Licence detectee", "Confiance (%)", "Source", "URL",
    "Raison du classement", "Chemin complet", "Date d'analyse",
]

# Couleur d'arriere-plan par categorie pour le rapport HTML (lisibilite
# rapide, comme demande implicitement par l'affichage type "Confiance : 98%").
_CATEGORY_COLORS = {
    "Commercial Use": "#f8d7da",
    "Personal Use Only": "#fff3cd",
    "OFL": "#d1e7dd",
    "Apache License": "#d1e7dd",
    "GPL": "#cfe2ff",
    "MIT": "#d1e7dd",
    "Public Domain": "#d1e7dd",
    "Shareware": "#ffe5b4",
    "Unknown": "#e2e3e5",
}


def _rows_to_dataframe(results: list[tuple[FontInfo, ClassificationResult]]) -> pd.DataFrame:
    rows = []
    for info, result in results:
        rows.append(
            {
                "Fichier": info.file_name,
                "Nom de la police": info.best_name,
                "Nom complet": info.full_name,
                "Designer": info.designer,
                "Editeur": info.manufacturer,
                "Version": info.version,
                "Licence detectee": result.category,
                "Confiance (%)": round(result.confidence * 100, 1),
                "Source": result.source,
                "URL": result.url,
                "Raison du classement": result.reason,
                "Chemin complet": info.file_path,
                "Date d'analyse": result.analyzed_at,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


def _write_csv(df: pd.DataFrame, destination: Path) -> Path:
    path = destination / "rapport.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")  # BOM : compatibilite Excel FR
    return path


def _write_xlsx(df: pd.DataFrame, destination: Path) -> Path:
    path = destination / "rapport.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Licences")
        worksheet = writer.sheets["Licences"]
        # Largeur de colonnes auto-ajustee (approximative mais lisible).
        for idx, column in enumerate(df.columns, start=1):
            max_len = max(len(str(column)), *(df[column].astype(str).map(len).tolist() or [0]))
            worksheet.column_dimensions[worksheet.cell(row=1, column=idx).column_letter].width = min(60, max_len + 2)
        worksheet.freeze_panes = "A2"

        # Mise en forme conditionnelle simple par categorie de licence.
        from openpyxl.styles import PatternFill
        category_col = df.columns.get_loc("Licence detectee") + 1
        for row_idx, category in enumerate(df["Licence detectee"], start=2):
            color = _CATEGORY_COLORS.get(category, "#ffffff").lstrip("#")
            fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            worksheet.cell(row=row_idx, column=category_col).fill = fill
    return path


def _write_html(df: pd.DataFrame, destination: Path, summary: dict[str, int]) -> Path:
    path = destination / "rapport.html"
    generated_at = datetime.now().strftime("%d/%m/%Y a %H:%M")

    summary_rows = "".join(
        f"<tr><td>{category}</td><td>{count}</td></tr>" for category, count in sorted(summary.items())
    )

    def style_row(category: str) -> str:
        color = _CATEGORY_COLORS.get(category, "#ffffff")
        return f'style="background-color:{color};"'

    body_rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{_escape(row[col])}</td>" for col in COLUMNS)
        body_rows.append(f'<tr {style_row(row["Licence detectee"])}>{cells}</tr>')

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Rapport de licences de polices</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f4efe6; color:#20201e; margin:0; padding:32px; }}
  h1 {{ margin-bottom:4px; }}
  .subtitle {{ color:#75716b; margin-bottom:28px; }}
  table {{ border-collapse: collapse; width:100%; background:#fffdfa; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  th, td {{ border:1px solid #d9d2c7; padding:8px 10px; font-size:13px; text-align:left; }}
  th {{ background:#20201e; color:#fffdfa; position:sticky; top:0; }}
  .summary {{ margin-bottom:28px; }}
  .summary table {{ width:auto; min-width:320px; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:bold; }}
</style>
</head>
<body>
  <h1>Rapport de classification des licences de polices</h1>
  <div class="subtitle">Genere le {generated_at} - {len(df)} police(s) analysee(s)</div>

  <div class="summary">
    <h2>Repartition par licence</h2>
    <table>
      <tr><th>Licence</th><th>Nombre de polices</th></tr>
      {summary_rows}
    </table>
  </div>

  <h2>Detail par police</h2>
  <table>
    <tr>{"".join(f"<th>{col}</th>" for col in COLUMNS)}</tr>
    {"".join(body_rows)}
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path


def _escape(value) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def generate_reports(
    results: list[tuple[FontInfo, ClassificationResult]], destination: Path
) -> dict[str, str]:
    """Genere les 3 formats de rapport et retourne leurs chemins."""
    destination.mkdir(parents=True, exist_ok=True)
    df = _rows_to_dataframe(results)

    summary: dict[str, int] = {}
    for _, result in results:
        summary[result.category] = summary.get(result.category, 0) + 1

    paths = {
        "csv": str(_write_csv(df, destination)),
        "xlsx": str(_write_xlsx(df, destination)),
        "html": str(_write_html(df, destination, summary)),
    }
    logger.info("Rapports generes dans %s", destination)
    return paths
