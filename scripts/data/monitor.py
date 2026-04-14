#!/usr/bin/env python3
"""
데이터 수집 진행 상황 모니터링 대시보드.

3개 파이프라인 (GitHub, Blog, Public)의 진행 상황을
한 터미널에서 실시간으로 보여줍니다.

사용법:
    python scripts/data/monitor.py

종료: Ctrl+C
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("rich 패키지가 필요합니다: pip install rich")
    exit(1)

console = Console()


def get_dir_size(path: Path) -> int:
    """디렉토리 전체 크기 계산 (bytes)."""
    if not path.exists():
        return 0
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total


def count_jsonl_lines(path: Path) -> int:
    """JSONL 파일들의 총 라인 수."""
    if not path.exists():
        return 0
    total = 0
    for f in path.rglob("*.jsonl"):
        try:
            with open(f) as fp:
                total += sum(1 for _ in fp)
        except Exception:
            pass
    return total


def count_subdirs(path: Path) -> int:
    """하위 디렉토리 개수."""
    if not path.exists():
        return 0
    return sum(1 for p in path.iterdir() if p.is_dir())


def format_size(bytes_: int) -> str:
    """바이트를 사람이 읽기 쉽게."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f}PB"


def format_number(n: int) -> str:
    """숫자에 콤마."""
    return f"{n:,}"


class DataMonitor:
    """데이터 수집 모니터."""

    def __init__(self, data_dir: Path, refresh_interval: float = 2.0):
        self.data_dir = data_dir
        self.refresh_interval = refresh_interval
        self.start_time = datetime.now()

        # 이전 통계 (속도 계산용)
        self.prev_stats: dict | None = None
        self.prev_time: datetime | None = None

    def get_stats(self) -> dict:
        """현재 통계 수집."""
        stats = {
            "github": {
                "repos": count_subdirs(self.data_dir / "raw" / "github"),
                "files": count_jsonl_lines(self.data_dir / "raw" / "github"),
                "size": get_dir_size(self.data_dir / "raw" / "github"),
            },
            "blogs": {
                "blogs": count_subdirs(self.data_dir / "raw" / "blogs"),
                "articles": count_jsonl_lines(self.data_dir / "raw" / "blogs"),
                "size": get_dir_size(self.data_dir / "raw" / "blogs"),
            },
            "public": {
                "files": len(list((self.data_dir / "raw" / "public").rglob("*.txt")))
                if (self.data_dir / "raw" / "public").exists() else 0,
                "size": get_dir_size(self.data_dir / "raw" / "public"),
            },
            "processed": {
                "size": get_dir_size(self.data_dir / "processed"),
            },
        }
        stats["total_size"] = (
            stats["github"]["size"]
            + stats["blogs"]["size"]
            + stats["public"]["size"]
            + stats["processed"]["size"]
        )
        return stats

    def calculate_speeds(self, current: dict) -> dict:
        """수집 속도 계산 (items/min)."""
        if self.prev_stats is None or self.prev_time is None:
            return {}

        elapsed = (datetime.now() - self.prev_time).total_seconds() / 60
        if elapsed < 0.01:
            return {}

        return {
            "github_files_per_min": (current["github"]["files"]
                                      - self.prev_stats["github"]["files"]) / elapsed,
            "blogs_per_min": (current["blogs"]["articles"]
                              - self.prev_stats["blogs"]["articles"]) / elapsed,
        }

    def make_layout(self) -> Layout:
        """레이아웃 생성."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        return layout

    def make_header(self) -> Panel:
        """헤더 패널."""
        elapsed = datetime.now() - self.start_time
        elapsed_str = str(elapsed).split(".")[0]

        text = Text()
        text.append("화랑 ", style="bold magenta")
        text.append("Hwarang AI ", style="bold cyan")
        text.append("- Data Collection Monitor\n", style="white")
        text.append(f"실행 시간: {elapsed_str}", style="dim")
        return Panel(text, border_style="cyan")

    def make_pipeline_table(self, stats: dict, speeds: dict) -> Table:
        """파이프라인 상태 테이블."""
        table = Table(title="📊 데이터 수집 현황", border_style="green")
        table.add_column("파이프라인", style="cyan", no_wrap=True)
        table.add_column("상태", justify="center")
        table.add_column("수집 항목", justify="right", style="green")
        table.add_column("크기", justify="right", style="yellow")
        table.add_column("속도", justify="right", style="magenta")

        # GitHub
        gh = stats["github"]
        gh_speed = speeds.get("github_files_per_min", 0)
        gh_status = "🟢 활성" if gh_speed > 0 else "⚪ 대기"
        table.add_row(
            "GitHub 크롤러",
            gh_status,
            f"{format_number(gh['repos'])} repos\n{format_number(gh['files'])} files",
            format_size(gh["size"]),
            f"{gh_speed:.0f}/min" if gh_speed > 0 else "-",
        )

        # Blogs
        bl = stats["blogs"]
        bl_speed = speeds.get("blogs_per_min", 0)
        bl_status = "🟢 활성" if bl_speed > 0 else "⚪ 대기"
        table.add_row(
            "기술 블로그",
            bl_status,
            f"{format_number(bl['blogs'])} blogs\n{format_number(bl['articles'])} 글",
            format_size(bl["size"]),
            f"{bl_speed:.0f}/min" if bl_speed > 0 else "-",
        )

        # Public datasets
        pb = stats["public"]
        pb_status = "🟢 활성" if pb["size"] > 0 else "⚪ 대기"
        table.add_row(
            "공개 데이터셋",
            pb_status,
            f"{format_number(pb['files'])} files",
            format_size(pb["size"]),
            "-",
        )

        return table

    def make_summary_panel(self, stats: dict) -> Panel:
        """요약 패널."""
        total_items = (
            stats["github"]["files"]
            + stats["blogs"]["articles"]
            + stats["public"]["files"]
        )

        text = Text()
        text.append("📈 전체 요약\n\n", style="bold")
        text.append(f"총 수집 항목:    ", style="dim")
        text.append(f"{format_number(total_items)}\n", style="green bold")
        text.append(f"총 데이터 크기:  ", style="dim")
        text.append(f"{format_size(stats['total_size'])}\n", style="yellow bold")
        text.append(f"정제된 데이터:   ", style="dim")
        text.append(f"{format_size(stats['processed']['size'])}\n", style="cyan bold")

        # 권장 데이터량 비교
        text.append("\n📏 학습 권장량 대비\n", style="bold")
        target_size_gb = 50  # 7B 모델 학습용 최소 권장
        current_gb = stats["total_size"] / 1e9
        progress_pct = min(100, (current_gb / target_size_gb) * 100)

        text.append(f"  목표:       50 GB\n", style="dim")
        text.append(f"  현재:       {current_gb:.1f} GB\n", style="dim")

        bar_width = 30
        filled = int(progress_pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        text.append(f"  [{bar}] {progress_pct:.1f}%\n",
                    style="green" if progress_pct > 80 else "yellow")

        return Panel(text, title="요약", border_style="green")

    def make_footer(self) -> Panel:
        """푸터."""
        text = Text()
        text.append("새로고침: ", style="dim")
        text.append(f"{self.refresh_interval}초", style="cyan")
        text.append("  |  종료: ", style="dim")
        text.append("Ctrl+C", style="red")
        return Panel(text, border_style="dim")

    def render(self) -> Layout:
        """전체 화면 렌더링."""
        layout = self.make_layout()
        stats = self.get_stats()
        speeds = self.calculate_speeds(stats)

        layout["header"].update(self.make_header())
        layout["main"]["left"].update(self.make_pipeline_table(stats, speeds))
        layout["main"]["right"].update(self.make_summary_panel(stats))
        layout["footer"].update(self.make_footer())

        # 다음 속도 계산을 위해 저장
        self.prev_stats = stats
        self.prev_time = datetime.now()

        return layout

    def run(self):
        """실행."""
        try:
            with Live(self.render(), refresh_per_second=1, console=console) as live:
                while True:
                    time.sleep(self.refresh_interval)
                    live.update(self.render())
        except KeyboardInterrupt:
            console.print("\n[yellow]모니터 종료됨[/yellow]")


def main():
    parser = argparse.ArgumentParser(description="데이터 수집 모니터")
    parser.add_argument("--data-dir", default="data", help="데이터 디렉토리")
    parser.add_argument("--refresh", type=float, default=2.0,
                       help="새로고침 간격 (초)")
    args = parser.parse_args()

    monitor = DataMonitor(
        data_dir=Path(args.data_dir),
        refresh_interval=args.refresh,
    )
    monitor.run()


if __name__ == "__main__":
    main()
