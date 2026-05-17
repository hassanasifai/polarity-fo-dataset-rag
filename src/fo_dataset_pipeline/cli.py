from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from fo_dataset_pipeline.io import read_records, read_sample_workbook_names, write_outputs
from fo_dataset_pipeline.models import RawFamilyOfficeRecord
from fo_dataset_pipeline.reports import write_reports
from fo_dataset_pipeline.validators import find_name_overlaps, validate_records

app = typer.Typer(no_args_is_help=True)

InputOption = Annotated[
    Path,
    typer.Option("--input", "-i"),
]
OutputDirOption = Annotated[
    Path,
    typer.Option("--output-dir", "-o"),
]
ReportDirOption = Annotated[
    Path,
    typer.Option("--report-dir", "-r"),
]
SampleWorkbookOption = Annotated[
    Path | None,
    typer.Option("--sample-workbook"),
]
RequiredCountOption = Annotated[
    int | None,
    typer.Option("--required-count"),
]


@app.command()
def validate(
    input: InputOption = Path("data/raw/family_offices_seed.csv"),
    output_dir: OutputDirOption = Path("data/processed"),
    report_dir: ReportDirOption = Path("reports"),
    sample_workbook: SampleWorkbookOption = Path(
        "../assements_details/FO-MAX-data-sample-2.0.xlsx"
    ),
    required_count: RequiredCountOption = None,
) -> None:
    """Validate family office records and write dataset/report artifacts."""
    raw_rows = read_records(input)
    records: list[RawFamilyOfficeRecord] = []
    errors: list[str] = []

    for index, row in enumerate(raw_rows, start=2):
        try:
            records.append(RawFamilyOfficeRecord.model_validate(row))
        except ValidationError as exc:
            errors.append(f"row {index}: {exc}")

    if errors:
        raise typer.BadParameter("\n".join(errors))

    if sample_workbook is not None:
        sample_names = read_sample_workbook_names(sample_workbook)
        overlaps = find_name_overlaps(
            [record.family_office_name for record in records],
            sample_names,
        )
        if overlaps:
            raise typer.BadParameter(
                "input contains names from the assessment sample workbook: "
                + ", ".join(sorted(overlaps))
            )

    validated = asyncio.run(validate_records(records))
    serializable = [
        record.model_dump(mode="json", exclude={"website_check", "source_checks"})
        | {
            "website_ok": record.website_check.ok,
            "website_status_code": record.website_check.status_code,
            "website_final_url": record.website_check.final_url,
            "sources_ok": sum(1 for check in record.source_checks if check.ok),
        }
        for record in validated
    ]
    write_outputs(serializable, output_dir, validated)
    write_reports(validated, report_dir)
    accepted = sum(1 for record in validated if record.validation_status == "accepted")
    typer.echo(
        f"Processed {len(validated)} records; "
        f"accepted {accepted}; reports written to {report_dir}"
    )
    if required_count is not None and accepted != required_count:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
