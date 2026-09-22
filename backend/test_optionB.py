import asyncio
from scraper.task_runner import TaskRunner


def on_progress(p):
    print(
        f"extracted={p.extracted}/{p.target} "
        f"skipped={p.skipped} "
        f"(no_email={p.skipped_no_email} "
        f"not_gmail={p.skipped_not_gmail} "
        f"year_mismatch={p.skipped_year_mismatch}) "
        f"scanned={p.scanned_users}",
        flush=True,
    )


async def main():
    runner = TaskRunner(on_progress=on_progress)
    result = await runner.run(
        target_count=2,
        location="Kazakhstan",
        min_repos=10,
        max_repos=20,
        start_year=2018,
        end_year=2022,
    )
    print("\n=== DONE ===")
    print("extracted:", result.extracted)
    print("run csv:", result.run_csv)
    if result.last_error:
        print("last_error:", result.last_error)


asyncio.run(main())