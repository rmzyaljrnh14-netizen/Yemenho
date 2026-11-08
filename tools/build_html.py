#!/usr/bin/env python3
"""Build a designed RTL Arabic HTML study from the Markdown documents."""
import re
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
OUT = ROOT / "dist" / "study.html"

# (filename, short Arabic label for the cover/TOC badge)
ORDER = [
    ("00-index-and-summary.md", "الفهرس والملخص التنفيذي"),
    ("01-feasibility-study.md", "دراسة الجدوى"),
    ("02-requirements-study.md", "دراسة المتطلبات"),
    ("03-PRD.md", "وثيقة متطلبات المنتج"),
    ("04-architecture.md", "المعمارية التقنية"),
    ("05-database-design.md", "تصميم قاعدة البيانات"),
    ("06-desktop-and-portal.md", "التطبيق والمنصة"),
    ("07-offline-and-sync.md", "العمل دون إنترنت والمزامنة"),
    ("08-security-and-testing.md", "الأمان والاختبارات"),
    ("09-indicator-library.md", "مكتبة المؤشرات"),
    ("10-implementation-plan.md", "مراحل التنفيذ"),
    ("11-governance-and-ownership.md", "الحوكمة والملكية"),
    ("12-national-rollout.md", "الربط الوطني والتوسّع"),
    ("13-api-specification.md", "واجهات الربط API"),
    ("14-sync-protocol.md", "بروتوكول المزامنة"),
    ("15-calculation-engine.md", "محرّك الحساب"),
    ("16-data-governance.md", "حوكمة البيانات والخصوصية"),
    ("17-dhis2-interoperability.md", "التكامل مع DHIS2"),
    ("18-nonfunctional-and-scaling.md", "المتطلبات الوطنية والتوسّع"),
    ("19-devops-and-updates.md", "التشغيل والتحديثات"),
    ("20-detailed-test-plan.md", "خطة الاختبار التفصيلية"),
    ("21-reports-and-dashboards.md", "التقارير ولوحات المعلومات"),
    ("22-quality-and-patient-safety.md", "الجودة وسلامة المرضى"),
    ("23-ai-assistant.md", "المساعد الذكي"),
    ("24-alerts-center.md", "مركز التنبيهات"),
    ("25-audit-log.md", "سجل التدقيق"),
    ("26-sync-monitor.md", "مركز المزامنة"),
    ("27-sync-alerts.md", "تنبيهات المزامنة"),
]

MD = markdown.Markdown(
    extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list", "md_in_html"],
    extension_configs={"toc": {"permalink": False}},
)


def normalize(text: str) -> str:
    """Ensure a blank line precedes every table so Python-Markdown parses it.

    Skips fenced code blocks so their contents are never altered.
    """
    lines = text.splitlines()
    out = []
    in_fence = False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(ln)
            continue
        if not in_fence and ln.lstrip().startswith("|") and out and out[-1].strip() and not out[-1].lstrip().startswith("|"):
            out.append("")
        out.append(ln)
    return "\n".join(out)


def convert(text: str):
    MD.reset()
    html = MD.convert(normalize(text))
    tokens = getattr(MD, "toc_tokens", [])
    return html, tokens


def split_title(text: str):
    lines = text.splitlines()
    title = None
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            title = ln[2:].strip()
            lines = lines[i + 1:]
            break
    return title, "\n".join(lines)


def render_toc(entries):
    rows = []
    for num, (fname, label), title, tokens in entries:
        subs = [t for t in tokens if t["level"] == 2]
        sub_html = "".join(
            f'<li><a href="#doc-{num}-{s["id"]}">{s["name"]}</a></li>' for s in subs
        )
        rows.append(
            f'<li class="toc-doc"><a class="toc-title" href="#doc-{num}">'
            f'<span class="toc-num">{num}</span>{title}</a>'
            f'<ul class="toc-sub">{sub_html}</ul></li>'
        )
    return '<ul class="toc">' + "".join(rows) + "</ul>"


def build():
    entries = []
    sections = []
    for num, (fname, label) in enumerate(ORDER, start=1):
        raw = (DOCS_DIR / fname).read_text(encoding="utf-8")
        title, body = split_title(raw)
        title = title or label
        html, tokens = convert(body)
        # Make heading anchors unique across the whole document.
        html = re.sub(r'<h([2-4]) id="([^"]+)"', lambda m: f'<h{m.group(1)} id="doc-{num}-{m.group(2)}"', html)
        entries.append((num, (fname, label), title, tokens))
        sections.append(
            f'<section class="doc" id="doc-{num}">'
            f'<header class="doc-head"><span class="doc-badge">وثيقة {num}</span>'
            f'<h1 class="doc-title">{title}</h1>'
            f'<span class="doc-tag">{label}</span></header>'
            f'{html}</section>'
        )

    toc_html = render_toc(entries)
    today = date.today().strftime("%Y-%m-%d")

    page = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>دراسة النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى — اليمن</title>
<style>{CSS}</style>
</head>
<body>
<div class="cover">
  <div class="cover-top">
    <div class="cover-mark">✚</div>
    <div class="cover-org">الجمهورية اليمنية · القطاع الصحي</div>
  </div>
  <div class="cover-mid">
    <div class="cover-kicker">المرحلة الأولى — تحليل وتصميم</div>
    <h1 class="cover-title">النظام الوطني لإدارة<br>مؤشرات الأداء الصحي<br>والجودة وسلامة المرضى</h1>
    <div class="cover-line"></div>
    <p class="cover-sub">دراسة متكاملة: الجدوى · المتطلبات · المعمارية · قاعدة البيانات · المزامنة · الأمان · المؤشرات · الحوكمة · الربط الوطني · واجهات API · خطة التنفيذ</p>
  </div>
  <div class="cover-meta">
    <div class="chip"><b>20</b><span>وثيقة</span></div>
    <div class="chip"><b>v1.1</b><span>الإصدار</span></div>
    <div class="chip"><b>{today}</b><span>التاريخ</span></div>
    <div class="chip warn"><b>بانتظار</b><span>الموافقة</span></div>
  </div>
  <div class="cover-note">لم يُكتب أي كود تنفيذي بعد · لم تُدَّعَ أي وظيفة بأنها تعمل</div>
</div>

<section class="doc toc-page">
  <header class="doc-head"><span class="doc-badge">المحتويات</span>
  <h1 class="doc-title">فهرس الدراسة</h1></header>
  {toc_html}
</section>

{''.join(sections)}
</body>
</html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT}  ({len(page):,} bytes, {len(sections)} documents)")


CSS = r"""
:root{
  --ink:#0f172a; --muted:#475569; --line:#e2e8f0;
  --brand:#0f766e; --brand-2:#115e59; --brand-soft:#ecfdf5;
  --accent:#b45309; --accent-soft:#fffbeb;
  --danger:#b91c1c;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:"Noto Naskh Arabic","Noto Sans Arabic",sans-serif;
  color:var(--ink); font-size:11.5pt; line-height:1.95;
  direction:rtl; text-align:right;
}
/* ---------- Cover ---------- */
.cover{
  height:257mm; width:100%;
  background:linear-gradient(150deg,#0f766e 0%,#115e59 45%,#0b3b38 100%);
  color:#fff; padding:20mm 18mm; display:flex; flex-direction:column;
  justify-content:space-between; page-break-after:always; position:relative; overflow:hidden;
}
.cover::after{
  content:""; position:absolute; inset:auto -60mm -80mm auto; width:200mm; height:200mm;
  background:radial-gradient(circle,rgba(255,255,255,.10),transparent 62%); border-radius:50%;
}
.cover-top{display:flex; align-items:center; gap:10px; justify-content:space-between}
.cover-mark{
  font-size:26pt; width:16mm; height:16mm; border-radius:4mm;
  background:rgba(255,255,255,.14); display:flex; align-items:center; justify-content:center;
  border:1px solid rgba(255,255,255,.3)
}
.cover-org{font-family:"Noto Kufi Arabic",sans-serif; font-size:11pt; letter-spacing:.5px; opacity:.92}
.cover-kicker{
  display:inline-block; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.35);
  padding:3px 12px; border-radius:20px; font-family:"Noto Kufi Arabic",sans-serif; font-size:10pt; margin-bottom:8mm
}
.cover-title{font-family:"Noto Kufi Arabic",sans-serif; font-size:30pt; line-height:1.5; margin:0 0 6mm; font-weight:700}
.cover-line{width:42mm; height:3px; background:#fbbf24; border-radius:3px; margin:0 0 6mm}
.cover-sub{font-size:12.5pt; opacity:.95; max-width:150mm; margin:0}
.cover-meta{display:flex; gap:6mm; flex-wrap:wrap}
.chip{
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.28);
  border-radius:4mm; padding:4mm 6mm; text-align:center; min-width:30mm
}
.chip b{display:block; font-family:"Noto Kufi Arabic",sans-serif; font-size:15pt}
.chip span{font-size:9pt; opacity:.85}
.chip.warn{background:rgba(251,191,36,.18); border-color:rgba(251,191,36,.5)}
.cover-note{font-size:9.5pt; opacity:.8; border-top:1px solid rgba(255,255,255,.25); padding-top:4mm}

/* ---------- Sections ---------- */
.doc{padding:0; margin:0 0 10mm}
.doc + .doc{page-break-before:always}
.doc-head{
  border-bottom:3px solid var(--brand); padding-bottom:4mm; margin-bottom:7mm;
  display:flex; flex-direction:column; gap:3px
}
.doc-badge{
  align-self:flex-start; background:var(--brand-soft); color:var(--brand-2);
  border:1px solid #99f6e4; border-radius:20px; padding:1px 12px;
  font-family:"Noto Kufi Arabic",sans-serif; font-size:9pt
}
.doc-title{font-family:"Noto Kufi Arabic",sans-serif; font-size:19pt; margin:2mm 0 0; line-height:1.5}
.doc-tag{color:var(--muted); font-size:10pt}
.toc-page .doc-head{border-bottom-color:var(--accent)}

/* ---------- Headings ---------- */
h2{
  font-family:"Noto Kufi Arabic",sans-serif; font-size:14.5pt; color:var(--brand-2);
  margin:8mm 0 3mm; padding-inline-start:4mm; border-inline-start:5px solid var(--brand);
  line-height:1.6; page-break-after:avoid
}
h3{font-family:"Noto Kufi Arabic",sans-serif; font-size:12.5pt; color:#0b3b38; margin:6mm 0 2mm; page-break-after:avoid}
h4{font-size:11.5pt; color:var(--muted); margin:4mm 0 1mm; page-break-after:avoid}
p{margin:0 0 2.6mm}
strong{color:#0b3b38}
a{color:var(--brand-2); text-decoration:none; word-break:break-word}
ul,ol{margin:0 0 3mm; padding-inline-start:7mm}
li{margin:0 0 1.2mm}

/* ---------- Blockquote = callout ---------- */
blockquote{
  background:var(--accent-soft); border:1px solid #fde68a; border-inline-start:5px solid var(--accent);
  border-radius:3mm; padding:4mm 5mm; margin:4mm 0; color:#5b4708
}
blockquote p:last-child{margin:0}

/* ---------- Tables ---------- */
table{
  width:100%; border-collapse:collapse; margin:4mm 0 5mm; font-size:10pt;
  page-break-inside:auto
}
thead{background:var(--brand); color:#fff}
th{
  font-family:"Noto Kufi Arabic",sans-serif; font-weight:600; padding:2.4mm 3mm;
  text-align:right; border:1px solid var(--brand-2); font-size:9.5pt
}
td{padding:2.2mm 3mm; border:1px solid var(--line); vertical-align:top}
tbody tr:nth-child(even){background:#f8fafc}
tr{page-break-inside:avoid}

/* ---------- Code ---------- */
code{
  font-family:"Noto Sans Mono","DejaVu Sans Mono",monospace; font-size:9pt;
  background:#f1f5f9; border:1px solid #e2e8f0; border-radius:2px; padding:0 3px
}
pre{
  direction:ltr; text-align:left; background:#0f172a; color:#e2e8f0;
  border-radius:3mm; padding:4mm 5mm; margin:4mm 0; overflow:auto;
  page-break-inside:avoid; border-inline-start:5px solid var(--brand)
}
pre code{background:transparent; border:0; color:inherit; font-size:9pt; line-height:1.7; padding:0}

/* ---------- TOC ---------- */
.toc{list-style:none; padding:0; margin:0}
.toc-doc{margin:0 0 4mm; padding-bottom:3mm; border-bottom:1px dashed var(--line); page-break-inside:avoid}
.toc-title{
  display:flex; align-items:center; gap:3mm; font-family:"Noto Kufi Arabic",sans-serif;
  font-size:12pt; color:var(--brand-2)
}
.toc-num{
  background:var(--brand); color:#fff; width:8mm; height:8mm; border-radius:2mm;
  display:inline-flex; align-items:center; justify-content:center; font-size:10pt
}
.toc-sub{list-style:none; padding-inline-start:11mm; margin:1.5mm 0 0; columns:2; column-gap:8mm}
.toc-sub li{font-size:9.5pt; color:var(--muted); margin:0 0 .8mm}

hr{border:0; border-top:1px solid var(--line); margin:6mm 0}
"""


if __name__ == "__main__":
    build()
