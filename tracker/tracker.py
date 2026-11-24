"""Spreadsheet helper for the job-search agent.

The agent never edits the spreadsheet directly. It calls this script, which
backs up the file, skips duplicates and writes rows in a consistent format.

Usage (from the repository root):
    python3 tracker/tracker.py seen              # JSON: postings already in the tracker + companies applied to
    python3 tracker/tracker.py add postings.json # add scored postings

Each posting in postings.json:
    {"id", "score", "company", "title", "location", "level", "why", "url"}
"""
import json
import os
import re
import shutil
import sys
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADERS = ["Date", "Score", "Company", "Role", "Location", "Level", "Why it fits / watch out", "Link", "Apply?", "ID"]
WIDTHS = [11, 9, 26, 46, 28, 14, 60, 18, 11, 13]
GREEN, YELLOW, BLUE = "C6EFCE", "FFEB9C", "2F4677"

# Words that say nothing about a role, ignored when comparing job titles.
STOP_WORDS = {"the", "and", "of", "for", "in", "de", "y", "a", "i", "ii", "jr", "junior", "start", "sep", "2026", "2027"}
SAME_ROLE_THRESHOLD = 0.6  # share of title words two roles must have in common


# ---------- config ----------

def load_config(path=None):
    path = path or os.path.join(ROOT, "config.json")
    if not os.path.exists(path):
        sys.exit("config.json not found. Copy config.example.json to config.json and edit it.")
    with open(path) as f:
        cfg = json.load(f)["tracker"]
    cfg["file"] = os.path.expanduser(cfg["file"])
    cfg["backup_dir"] = os.path.expanduser(cfg.get("backup_dir") or os.path.dirname(cfg["file"]))
    return cfg


# ---------- text helpers (pure functions, easy to test) ----------

def normalize(text):
    """'Novo Nordisk A/S' -> 'novonordiskas'. Used to compare company names."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def title_words(text):
    """Meaningful words of a job title, e.g. 'QC Analyst I' -> {'analyst'}."""
    words = re.findall(r"[a-z0-9áéíóúñü]+", (text or "").lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def company_key(name):
    """Drop anything in brackets: 'Sanofi (Waterford)' -> 'sanofi'."""
    return normalize(str(name).split("(")[0])


def same_role(company_a, title_a, company_b, title_b):
    """True if two postings look like the same role at the same company."""
    a, b = company_key(company_a), company_key(company_b)
    if not a or not b or not (a in b or b in a):
        return False
    wa, wb = title_words(title_a), title_words(title_b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= SAME_ROLE_THRESHOLD


def score_color(score):
    return GREEN if score >= 8 else YELLOW if score >= 6 else None


# ---------- spreadsheet ----------

def check_not_open(path):
    """Excel creates '~$name.xlsx' while a file is open. Writing then loses data."""
    lock = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path))
    if os.path.exists(lock):
        sys.exit(f"{os.path.basename(path)} is open in Excel. Close it and run again.")


def open_workbook(cfg):
    if os.path.exists(cfg["file"]):
        return openpyxl.load_workbook(cfg["file"])
    wb = openpyxl.Workbook()
    wb.active.title = cfg["applications_sheet"]
    return wb


def new_postings_sheet(wb, name):
    if name in wb.sheetnames:
        return wb[name]
    ws = wb.create_sheet(name)
    ws.append(HEADERS)
    for i, width in enumerate(WIDTHS, start=1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BLUE)
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"
    choices = DataValidation(type="list", formula1='"Yes,No,Applied"', allow_blank=True)
    ws.add_data_validation(choices)
    choices.add("I2:I5000")
    return ws


def applied_roles(wb, cfg):
    """(company, role, row number) for every application already sent."""
    if cfg["applications_sheet"] not in wb.sheetnames:
        return []
    ws = wb[cfg["applications_sheet"]]
    company_col = column_index_from_string(cfg["company_column"]) - 1
    role_col = column_index_from_string(cfg["role_column"]) - 1
    rows = ws.iter_rows(min_row=cfg["applications_first_row"], values_only=True)
    return [(r[company_col], r[role_col], i) for i, r in enumerate(rows, start=1) if r[company_col]]


def seen_ids(wb, cfg):
    if cfg["new_postings_sheet"] not in wb.sheetnames:
        return set()
    ws = wb[cfg["new_postings_sheet"]]
    return {str(r[9]) for r in ws.iter_rows(min_row=2, values_only=True) if len(r) > 9 and r[9]}


# ---------- commands ----------

def cmd_seen(cfg):
    wb = open_workbook(cfg)
    applied = sorted({company_key(c) for c, _, _ in applied_roles(wb, cfg)})
    print(json.dumps({"seen_ids": sorted(seen_ids(wb, cfg)), "applied_companies": applied}))


def cmd_add(cfg, postings_file):
    with open(postings_file) as f:
        postings = json.load(f)
    check_not_open(cfg["file"])
    if os.path.exists(cfg["file"]):
        os.makedirs(cfg["backup_dir"], exist_ok=True)
        backup = os.path.join(cfg["backup_dir"], f"backup_{datetime.now():%Y%m%d_%H%M}.xlsx")
        shutil.copy(cfg["file"], backup)

    wb = open_workbook(cfg)
    ws = new_postings_sheet(wb, cfg["new_postings_sheet"])
    known = seen_ids(wb, cfg)
    applied = applied_roles(wb, cfg)

    added = 0
    for p in sorted(postings, key=lambda p: -p["score"]):
        if str(p["id"]) in known:
            continue
        match = next((n for c, r, n in applied if same_role(p["company"], p["title"], c, r)), None)
        if match:
            print(f"skipped (already applied, #{match}): {p['company']} - {p['title']}")
            continue

        ws.append([date.today(), p["score"], p["company"], p["title"], p.get("location", ""),
                   p.get("level", ""), p.get("why", ""), "open", None, str(p["id"])])
        row = ws.max_row
        ws.cell(row, 1).number_format = "DD/MM/YY"
        ws.cell(row, 8).hyperlink = p["url"]
        ws.cell(row, 8).font = Font(color="0563C1", underline="single")
        if score_color(p["score"]):
            ws.cell(row, 2).fill = PatternFill("solid", fgColor=score_color(p["score"]))
        for col in range(1, 11):
            ws.cell(row, col).alignment = Alignment(vertical="top", wrap_text=col in (4, 7))
        known.add(str(p["id"]))
        added += 1

    wb.save(cfg["file"])
    print(f"added {added} postings to '{cfg['new_postings_sheet']}'")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("seen", "add") or (sys.argv[1] == "add" and len(sys.argv) < 3):
        sys.exit(__doc__)
    config = load_config()
    if sys.argv[1] == "seen":
        cmd_seen(config)
    else:
        cmd_add(config, sys.argv[2])
