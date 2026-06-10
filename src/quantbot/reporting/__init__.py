"""Reporting: charts, comparison tables, research dossiers.

Pure-stdlib SVG/HTML rendering so reports generate anywhere (CI, containers,
air-gapped research boxes) without plotting dependencies.
"""

from quantbot.reporting.charts import drawdown_svg, equity_svg
from quantbot.reporting.research_report import write_research_report

__all__ = ["equity_svg", "drawdown_svg", "write_research_report"]
