"""PDF Report Generation Service using PyMuPDF (P2.12)."""

from __future__ import annotations

import datetime
from typing import Any

import pymupdf


class PDFReportCanvas:
    """Helper to draw multi-page clean academic reports with standard A4 geometry."""

    def __init__(self, title: str, subtitle: str = ""):
        self.doc = pymupdf.open()
        self.report_title = title
        self.report_subtitle = subtitle
        self.page_width = 595.0  # A4 width in points
        self.page_height = 842.0  # A4 height in points
        self.margin = 40.0
        self.content_width = self.page_width - (2 * self.margin)
        self.max_y = self.page_height - 50.0
        self.page: pymupdf.Page = None  # type: ignore[assignment]
        self.y = self.margin
        self.page_num = 0

        self.new_page(is_first=True)

    def new_page(self, is_first: bool = False) -> None:
        self.page = self.doc.new_page(width=self.page_width, height=self.page_height)
        self.page_num += 1
        self.y = self.margin

        # Top decorative accent bar
        top_bar = pymupdf.Rect(self.margin, self.y, self.margin + self.content_width, self.y + 4)
        self.page.draw_rect(top_bar, color=None, fill=(0.74, 0.38, 0.24))  # Parakh terracotta
        self.y += 14

        if is_first:
            # Header banner
            header_rect = pymupdf.Rect(
                self.margin, self.y, self.margin + self.content_width, self.y + 54
            )
            self.page.draw_rect(header_rect, color=None, fill=(0.16, 0.19, 0.22))  # Dark slate
            self.page.insert_text(
                (self.margin + 16, self.y + 24),
                self.report_title,
                fontsize=14,
                color=(1.0, 1.0, 1.0),
                fontname="helv",
            )
            if self.report_subtitle:
                self.page.insert_text(
                    (self.margin + 16, self.y + 42),
                    self.report_subtitle[:95],
                    fontsize=9,
                    color=(0.82, 0.84, 0.86),
                    fontname="helv",
                )
            self.y += 70
        else:
            # Running header on continuation pages
            self.page.insert_text(
                (self.margin, self.y + 10),
                f"{self.report_title} (Continued)",
                fontsize=9,
                color=(0.4, 0.45, 0.5),
                fontname="helv",
            )
            self.page.draw_line(
                pymupdf.Point(self.margin, self.y + 16),
                pymupdf.Point(self.margin + self.content_width, self.y + 16),
                color=(0.85, 0.85, 0.85),
                width=0.75,
            )
            self.y += 30

    def ensure_space(self, height: float) -> None:
        if self.y + height > self.max_y:
            self.new_page()

    def draw_section_heading(self, text: str) -> None:
        self.ensure_space(28)
        self.page.insert_text(
            (self.margin, self.y + 12),
            text.upper(),
            fontsize=11,
            color=(0.15, 0.18, 0.21),
            fontname="helv",
        )
        self.page.draw_line(
            pymupdf.Point(self.margin, self.y + 17),
            pymupdf.Point(self.margin + self.content_width, self.y + 17),
            color=(0.8, 0.8, 0.8),
            width=1.0,
        )
        self.y += 26

    def draw_kpi_cards(self, cards: list[tuple[str, str]]) -> None:
        """Draw 2 to 4 KPI metric cards in a responsive horizontal grid."""
        if not cards:
            return
        self.ensure_space(55)
        num_cards = len(cards)
        card_gap = 10.0
        total_gaps = (num_cards - 1) * card_gap
        card_w = (self.content_width - total_gaps) / num_cards
        card_h = 46.0

        for idx, (label, val) in enumerate(cards):
            x0 = self.margin + idx * (card_w + card_gap)
            x1 = x0 + card_w
            rect = pymupdf.Rect(x0, self.y, x1, self.y + card_h)
            self.page.draw_rect(rect, color=(0.85, 0.85, 0.85), fill=(0.97, 0.96, 0.95), width=0.75)
            self.page.insert_text(
                (x0 + 8, self.y + 16),
                label.upper(),
                fontsize=7.5,
                color=(0.45, 0.48, 0.52),
                fontname="helv",
            )
            self.page.insert_text(
                (x0 + 8, self.y + 36),
                str(val),
                fontsize=14,
                color=(0.15, 0.18, 0.21),
                fontname="helv",
            )
        self.y += card_h + 16

    def draw_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        col_widths: list[float] | None = None,
    ) -> None:
        """Render a formatted multi-column data table with auto page-wrapping."""
        num_cols = len(headers)
        if not col_widths or len(col_widths) != num_cols:
            col_widths = [self.content_width / num_cols] * num_cols

        # Header row
        self.ensure_space(24)
        th_rect = pymupdf.Rect(self.margin, self.y, self.margin + self.content_width, self.y + 20)
        self.page.draw_rect(th_rect, color=None, fill=(0.93, 0.91, 0.89))

        curr_x = self.margin
        for col_idx, th in enumerate(headers):
            w = col_widths[col_idx]
            self.page.insert_text(
                (curr_x + 6, self.y + 13),
                th.upper(),
                fontsize=7.5,
                color=(0.3, 0.33, 0.36),
                fontname="helv",
            )
            curr_x += w
        self.y += 20

        if not rows:
            self.ensure_space(20)
            self.page.insert_text(
                (self.margin + 8, self.y + 13),
                "No records available.",
                fontsize=8.5,
                color=(0.55, 0.58, 0.6),
                fontname="helv",
            )
            self.y += 20
            return

        # Data rows
        for r_idx, row in enumerate(rows):
            self.ensure_space(18)
            row_bg = (0.98, 0.98, 0.98) if r_idx % 2 == 1 else (1.0, 1.0, 1.0)
            tr_rect = pymupdf.Rect(
                self.margin, self.y, self.margin + self.content_width, self.y + 18
            )
            self.page.draw_rect(tr_rect, color=(0.92, 0.92, 0.92), fill=row_bg, width=0.5)

            curr_x = self.margin
            for col_idx, val in enumerate(row[:num_cols]):
                w = col_widths[col_idx]
                text_val = str(val or "—")
                # Truncate text if it would visually overflow the column width
                max_chars = max(4, int(w / 5.2))
                if len(text_val) > max_chars:
                    text_val = text_val[: max_chars - 2] + ".."
                self.page.insert_text(
                    (curr_x + 6, self.y + 12),
                    text_val,
                    fontsize=8.0,
                    color=(0.18, 0.2, 0.22),
                    fontname="helv",
                )
                curr_x += w
            self.y += 18

        self.y += 12

    def draw_paragraph(
        self, text: str, fontsize: float = 8.5, color: tuple = (0.3, 0.35, 0.4)
    ) -> None:
        """Render a wrapped multi-line paragraph block."""
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            if len(" ".join(current_line)) > 88:
                lines.append(" ".join(current_line))
                current_line = []
        if current_line:
            lines.append(" ".join(current_line))

        needed = len(lines) * 12 + 6
        self.ensure_space(needed)
        for line in lines:
            self.page.insert_text(
                (self.margin, self.y + 10), line, fontsize=fontsize, color=color, fontname="helv"
            )
            self.y += 12
        self.y += 8

    def tobytes(self) -> bytes:
        total = len(self.doc)
        for idx, page in enumerate(self.doc, 1):
            footer_text = f"Parakh AI Oral Examination System  •  Page {idx} of {total}"
            page.insert_text(
                (self.margin, self.page_height - 24),
                footer_text,
                fontsize=7.5,
                color=(0.55, 0.58, 0.6),
                fontname="helv",
            )
            confidential_note = "Academic Record — Confidential"
            page.insert_text(
                (self.page_width - self.margin - 140, self.page_height - 24),
                confidential_note,
                fontsize=7.5,
                color=(0.55, 0.58, 0.6),
                fontname="helv",
            )
        return self.doc.tobytes()


def generate_student_report_pdf(report: dict[str, Any]) -> bytes:
    """Generate a clean, professional PDF performance report for an individual student."""
    student_name = report.get("student", {}).get("full_name") or "Student"
    student_email = report.get("student", {}).get("email") or ""
    now_str = datetime.datetime.now(datetime.UTC).strftime("%B %d, %Y")

    subtitle = f"Student: {student_name} ({student_email})  •  Generated on {now_str}"
    canvas = PDFReportCanvas("STUDENT ORAL PERFORMANCE REPORT", subtitle)

    overall = report.get("overall", {})
    total_sessions = overall.get("total_sessions", 0)
    completed_sessions = overall.get("completed_sessions", 0)
    avg_score_pct = overall.get("average_score_percent") or "—"
    answers_count = overall.get("total_evaluated_answers", 0)

    # Key Performance Indicators
    canvas.draw_section_heading("Executive Summary")
    canvas.draw_kpi_cards(
        [
            ("Completed Vivas", str(completed_sessions)),
            ("Total Attempts", str(total_sessions)),
            ("Average Score", str(avg_score_pct)),
            ("Evaluated Answers", str(answers_count)),
        ]
    )

    # Core Dimensions (Rubrics)
    dims = overall.get("dimension_averages") or {}
    cor = dims.get("correctness")
    cmp = dims.get("completeness")
    cla = dims.get("clarity")
    if cor is not None or cmp is not None or cla is not None:
        canvas.draw_section_heading("Oral Competency Dimensions")
        canvas.draw_kpi_cards(
            [
                ("Factual Correctness", f"{round(cor * 100)}%" if cor is not None else "—"),
                ("Answer Completeness", f"{round(cmp * 100)}%" if cmp is not None else "—"),
                ("Spoken Clarity", f"{round(cla * 100)}%" if cla is not None else "—"),
            ]
        )

    # Topic Breakdown
    topics = report.get("topic_breakdown") or []
    canvas.draw_section_heading("Topic-Wise Oral Performance")
    headers = ["Topic Name", "Course", "Questions", "Score", "Classification"]
    col_w = [185.0, 110.0, 60.0, 60.0, 100.0]
    rows = []
    for t in topics:
        st = (t.get("status") or "developing").title()
        rows.append(
            [
                t.get("topic_name", "Topic"),
                t.get("course_code") or t.get("course_name") or "Course",
                str(t.get("evaluated_count", 0)),
                t.get("average_score_percent", "—"),
                st,
            ]
        )
    canvas.draw_table(headers, rows, col_w)

    # Diagnostic Coaching Note
    coaching = report.get("coaching_summary")
    if coaching:
        canvas.draw_section_heading("AI Diagnostic Insights & Coaching Guidance")
        canvas.draw_paragraph(coaching)

    # Recent Attempts History
    attempts = report.get("recent_attempts") or []
    canvas.draw_section_heading("Recent Examination & Viva History")
    att_headers = ["Date", "Course", "Title / Type", "Status", "Score"]
    att_col_w = [90.0, 105.0, 190.0, 70.0, 60.0]
    att_rows = []
    for a in attempts[:15]:
        created = a.get("created_at") or ""
        date_display = created[:10] if len(created) >= 10 else "—"
        att_rows.append(
            [
                date_display,
                a.get("course_code") or a.get("course_name") or "Course",
                a.get("title") or "Practice Viva",
                (a.get("status") or "completed").title(),
                a.get("score_percent") or "—",
            ]
        )
    canvas.draw_table(att_headers, att_rows, att_col_w)

    return canvas.tobytes()


def generate_class_report_pdf(report: dict[str, Any]) -> bytes:
    """Generate a clean, readable PDF class examination report for teachers."""
    course_title = report.get("course_name") or "All Assigned Courses"
    course_code = report.get("course_code") or ""
    teacher_name = report.get("teacher_name") or "Instructor"
    now_str = datetime.datetime.now(datetime.UTC).strftime("%B %d, %Y")

    subtitle = f"Course: {course_title} {f'({course_code})' if course_code else ''}  •  Instructor: {teacher_name}  •  {now_str}"
    canvas = PDFReportCanvas("CLASS ORAL EXAMINATION REPORT", subtitle)

    summary = report.get("summary", {})
    canvas.draw_section_heading("Class Summary Metrics")
    canvas.draw_kpi_cards(
        [
            ("Active Students", str(summary.get("total_students", 0))),
            ("Total Sessions", str(summary.get("total_sessions", 0))),
            ("Completed Vivas", str(summary.get("completed_sessions", 0))),
            ("Class Average", str(summary.get("average_score_percent", "—"))),
        ]
    )

    # Score Distribution
    dist = report.get("score_distribution")
    if dist:
        canvas.draw_section_heading("Class Score Distribution")
        canvas.draw_kpi_cards(
            [
                ("Mastery (80%+)", f"{dist.get('mastery', 0)} ({dist.get('mastery_pct', '0%')})"),
                (
                    "Proficient (65-79%)",
                    f"{dist.get('proficient', 0)} ({dist.get('proficient_pct', '0%')})",
                ),
                (
                    "Developing (50-64%)",
                    f"{dist.get('developing', 0)} ({dist.get('developing_pct', '0%')})",
                ),
                (
                    "Needs Attention (<50%)",
                    f"{dist.get('attention', 0)} ({dist.get('attention_pct', '0%')})",
                ),
            ]
        )

    # Class-wide Weak Topics
    weaknesses = report.get("class_weaknesses") or []
    if weaknesses:
        canvas.draw_section_heading("Identified Class-Wide Weak Topics")
        weak_headers = ["Topic", "Course", "Attempts", "Average Score", "Recommendation"]
        weak_col_w = [140.0, 95.0, 55.0, 65.0, 160.0]
        weak_rows = []
        for w in weaknesses:
            weak_rows.append(
                [
                    w.get("topic_name", "Topic"),
                    w.get("course_name", "Course"),
                    str(w.get("attempt_count", 0)),
                    w.get("average_score_percent", "—"),
                    w.get("recommendation") or "Review core conceptual framework with class.",
                ]
            )
        canvas.draw_table(weak_headers, weak_rows, weak_col_w)

    # Student Roster & Performance
    students = report.get("students") or []
    canvas.draw_section_heading("Student Performance Roster")
    stu_headers = ["Student Name", "Email", "Vivas", "Completed", "Average", "Last Active"]
    stu_col_w = [115.0, 140.0, 50.0, 60.0, 60.0, 90.0]
    stu_rows = []
    for s in students:
        last_dt = (s.get("last_active_at") or "")[:10] or "—"
        stu_rows.append(
            [
                s.get("student_name", "Student"),
                s.get("student_email", ""),
                str(s.get("total_sessions", 0)),
                str(s.get("completed_sessions", 0)),
                s.get("average_score_percent", "—"),
                last_dt,
            ]
        )
    canvas.draw_table(stu_headers, stu_rows, stu_col_w)

    return canvas.tobytes()
