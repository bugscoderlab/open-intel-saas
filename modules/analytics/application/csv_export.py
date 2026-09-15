"""CSV export (ticket #57): render any registered metric's result as
RFC 4180-ish CSV from the SAME metric functions the JSON endpoints run —
no separate export pipeline (spec assumption 7). Columns are the union
of point keys in first-appearance order.
"""

import csv
import io
from datetime import UTC, datetime

from modules.analytics.domain.entities import MetricResult


def metric_to_csv(result: MetricResult) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    columns: list[str] = []
    for point in result.points:
        for key in point:
            if key not in columns:
                columns.append(key)
    writer.writerow(["metric", result.metric, "unit", result.unit])
    writer.writerow(columns)
    for point in result.points:
        writer.writerow([point.get(column) for column in columns])
    return buffer.getvalue()


def export_filename(metric: str) -> str:
    today = datetime.now(UTC).date().isoformat()
    return f"{metric}-{today}.csv"
