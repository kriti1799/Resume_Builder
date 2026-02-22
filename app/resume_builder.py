"""
Resume Tailoring Agent — two steps: (1) enhance info.json for job + ATS, (2) fill template structure only.

Step 1 – Enhance content: Take info.json and job description. LLM improves wording for the specific
job and for ATS scoring, using ONLY info.json (no invented details). Do not change sentence lengths
by a lot so content still fits. Output: enhanced structured content (JSON).

Step 2 – Use template only for structure: template.tex is used ONLY for section headers, lines,
margins, and LaTeX commands (\\resumeItem, \\section, etc.). Create a new .tex with that structure
and fill it entirely with the enhanced content from Step 1. Do not copy the template's example
body text — only headers, lines, margins.

Finally: compile to PDF (pdf/resume_<Name>.pdf).
Requires: OpenAI API key in json/config.json, pdflatex on PATH.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
JSON_DIR = SCRIPT_DIR / "json"
PDF_DIR = SCRIPT_DIR / "pdf"
TEX_DIR = SCRIPT_DIR / "tex"
LINK_FILE = SCRIPT_DIR / "link.txt"
INFO_FILE = JSON_DIR / "info.json"
CONFIG_FILE = JSON_DIR / "config.json"
TEMPLATE_TEX = TEX_DIR / "template.tex"
OUTPUT_DIR = PDF_DIR


def _first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def load_config() -> dict:
    config_path = _first_existing(CONFIG_FILE, PROJECT_DIR / "json" / "config.json")
    if not config_path:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_job_link(link_path: Path) -> str:
    with open(link_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    raise ValueError("No valid URL in link.txt")


def fetch_job_description(url: str) -> str:
    def _render_with_playwright(target_url: str) -> str | None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                selectors = ["[data-job-description]", ".job-description", "article", "main", "body"]
                for sel in selectors:
                    try:
                        el = page.query_selector(sel)
                        if not el:
                            continue
                        txt = (el.inner_text() or "").strip()
                        if len(txt) > 200:
                            browser.close()
                            return txt
                    except Exception:
                        continue

                browser.close()
        except Exception:
            return None
        return None

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        if requests:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            raw_html = resp.text
        else:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[Could not fetch: {e}]"

    if BeautifulSoup:
        soup = BeautifulSoup(raw_html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                desc = data.get("description") or (data.get("@graph", [{}])[0].get("description") if isinstance(data.get("@graph"), list) else None)
                if desc:
                    return desc
            except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                pass
        for sel in ["[data-job-description]", ".job-description", "article", "main"]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(separator="\n", strip=True)
                if len(t) > 200:
                    return t
        title = soup.find("title")
        if title and title.string:
            title_text = title.string.strip()
            rendered = _render_with_playwright(url)
            if rendered:
                return rendered
            return f"Job: {title_text}"
    else:
        scripts = re.findall(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            raw_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for script_body in scripts:
            try:
                data = json.loads(script_body.strip() or "{}")
                desc = data.get("description")
                if not desc and isinstance(data.get("@graph"), list):
                    first = data.get("@graph")[0] or {}
                    desc = first.get("description")
                if desc:
                    return str(desc)
            except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                pass

        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            return text[:12000]

        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            rendered = _render_with_playwright(url)
            if rendered:
                return rendered
            return f"Job: {title_match.group(1).strip()}"

    rendered = _render_with_playwright(url)
    if rendered:
        return rendered
    return "[Job page structure not recognized.]"


def load_user_info(info_path: Path) -> dict:
    with open(info_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_template(template_path: Path) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def _openai_client():
    config = load_config()
    api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set openai_api_key in app/json/config.json, json/config.json, or OPENAI_API_KEY.")
    return OpenAI(api_key=api_key), config.get("openai_model") or "gpt-4o"


# --- Step 1: Enhance info.json for the job (ATS-friendly, similar sentence length) ---
def llm_enhance_for_job(user_info: dict, job_description: str) -> dict:
    """
    LLM improves the resume content from info.json for the specific job and for ATS.
    Uses only info.json; does not change sentence lengths by much so content still fits.
    Returns enhanced structured content (dict) for use in the template.
    """
    if not OpenAI or not user_info:
        return user_info
    client, model = _openai_client()
    prompt = f"""You are an expert resume writer. You will receive info.json (structured resume data) and a job description.

Your task: Produce a single JSON object with ENHANCED resume content that:
1) Is tailored for this specific job and would score highly if scanned by an ATS (use keywords from the job, clear section structure, quantifiable achievements).
2) Uses ONLY information from info.json — do not invent any details, dates, or facts.
3) Does NOT change the length of each sentence by a lot — keep roughly the same length so the content still fits on the page. Improve wording and emphasis, not length.
4) Include ONLY the sections that exist in info.json. Do NOT add any section that is not in the source (e.g. do not add summary, objective, or profile if they are not in info.json). Use the same top-level keys as the input (e.g. personal_info, education, work_experience, projects, skills, certifications, publications). If a key is missing or empty in info.json, omit it from your output.

Output shape (JSON only, no markdown): Use only keys present in the provided info.json (e.g. personal_info, education, work_experience, projects, skills, certifications, publications). Return ONLY valid JSON. No code fence, no explanation.

JOB DESCRIPTION:
{job_description[:8000]}

INFO.JSON (only source of content — enhance wording for job and ATS, keep sentence lengths similar):
{json.dumps(user_info, indent=2)[:30000]}
"""

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return user_info


# --- Step 2: Use template ONLY for headers, lines, margins; fill with enhanced content ---
def llm_fill_template_structure_only(enhanced_content: dict, template_content: str) -> str:
    """
    Use template.tex ONLY for: section headers, lines (titlerule), margins (preamble), and
    LaTeX command definitions (\\resumeItem, \\resumeSubheading, etc.). Create a new .tex
    whose body is entirely the enhanced content — do not copy the template's example body text.
    """
    if not OpenAI or not enhanced_content:
        return template_content
    client, model = _openai_client()
    prompt = f"""You are a LaTeX expert. You will receive (1) enhanced resume content (JSON) and (2) template.tex.

Your task: Produce a complete .tex file where:
- The template is used ONLY for: the preamble (margins, fonts, packages), section HEADERS and formatting (e.g. \\section{{Education}}, \\section{{Experience}}), horizontal lines (\\titlerule), and the command definitions (\\resumeItem, \\resumeSubheading, \\resumeProjectHeading, \\resumeItemListStart, etc.). Use the template's margins and layout structure.
- Do NOT copy any of the template's example or placeholder BODY text (names, bullet points, company names, etc.). All body content must come from the enhanced content JSON below. Replace every example line with the corresponding enhanced text.
- Fill the document body ONLY with sections that exist in the enhanced content JSON. Do NOT add a Summary, Objective, Profile, or any section that is not present in the JSON. For example, if there is no "summary" key (or it is missing/empty), do not output a summary section. Include: header block (from personal_info), then only those sections that appear in the JSON (education, work_experience, projects, skills, certifications, publications, etc.). Use the same LaTeX commands as the template (\\resumeItem, \\resumeSubheading, etc.) but with your enhanced text only.

LATEX RULES (required for compilation):
- Escape special characters in inserted text: % → \\%, & → \\&, # → \\#, _ → \\_. For literal curly braces in text use \\{{ and \\}}.
- Every \\resumeItem has one argument: \\resumeItem{{content}}. No unescaped {{ or }} inside the content.

Return ONLY the full LaTeX source from \\documentclass to \\end{{document}}. No markdown, no code fence, no explanation.

ENHANCED RESUME CONTENT (use this for all body text; template only for headers/lines/margins/commands):
{json.dumps(enhanced_content, indent=2)[:28000]}

TEMPLATE.TEX (use only for preamble, section headers, lines, margins, and command structure — not for body text):
{template_content}
"""

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return raw


def compile_latex_to_pdf(tex_path: Path, output_dir: Path, jobname: str) -> tuple[Path | None, str]:
    """Compile .tex to PDF with pdflatex. Returns (pdf_path, "") or (None, error_message)."""
    if not tex_path.exists():
        return (None, f"TeX file not found: {tex_path}")
    output_dir = output_dir.resolve()
    cwd = SCRIPT_DIR
    try:
        rel_tex = tex_path.resolve().relative_to(cwd)
    except ValueError:
        rel_tex = tex_path
    args = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        f"-jobname={jobname}",
        str(rel_tex).replace("\\", "/"),
    ]
    try:
        for _ in range(2):
            result = subprocess.run(
                args, cwd=cwd, capture_output=True, timeout=120, text=True, encoding="utf-8", errors="replace"
            )
            pdf_path = output_dir / f"{jobname}.pdf"
            if result.returncode != 0:
                # pdflatex can return non-zero with warnings while still producing a usable PDF.
                if pdf_path.exists() and pdf_path.stat().st_size > 500:
                    continue
                err = (result.stderr or result.stdout or "").strip()
                last_lines = "\n".join(err.splitlines()[-40:]) if err else "No output"
                return (None, f"pdflatex exit code {result.returncode}:\n{last_lines}")
        if pdf_path.exists() and pdf_path.stat().st_size > 500:
            return (pdf_path, "")
        return (None, "pdflatex ran but no PDF was produced.")
    except FileNotFoundError:
        return (
            None,
            "pdflatex not found. Install TeX (MiKTeX or TeX Live) and add it to PATH.",
        )
    except subprocess.TimeoutExpired:
        return (None, "pdflatex timed out after 120 seconds.")
    except Exception as e:
        return (None, str(e))


def get_pdf_page_count_from_log(output_dir: Path, jobname: str) -> int:
    """Read pdflatex .log and return page count (e.g. 1 or 2). Returns 1 if unreadable."""
    log_path = output_dir / f"{jobname}.log"
    if not log_path.exists():
        return 1
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"Output written on .+ \((\d+)\s+page", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 1


def reduce_tex_spacing(tex_content: str) -> str:
    """Make spaces between sections smaller so the resume fits on one page."""
    # Match \vspace{-Npt}, \vspace{-N mm}, \vspace{-Nmm}
    def tighten(match: re.Match) -> str:
        num, unit = int(match.group(1)), match.group(2).strip().lower()
        if unit == "pt" and -25 <= num <= -1:
            return f"\\vspace{{{max(-24, num * 2)}pt}}"
        if unit == "mm" and -25 <= num <= -1:
            return f"\\vspace{{{max(-10, num * 2)}mm}}"
        return match.group(0)
    tex_content = re.sub(r"\\vspace\{\s*(-?\d+)\s*(pt|mm)\s*\}", tighten, tex_content)
    # Tighten common fixed values (in case regex missed any)
    replacements = [
        ("\\vspace{-4pt}", "\\vspace{-8pt}"),
        ("\\vspace{-5pt}", "\\vspace{-10pt}"),
        ("\\vspace{-6pt}", "\\vspace{-12pt}"),
        ("\\vspace{-7pt}", "\\vspace{-14pt}"),
        ("\\vspace{-8pt}", "\\vspace{-16pt}"),
        ("\\vspace{-12pt}", "\\vspace{-18pt}"),
        ("\\vspace{-15pt}", "\\vspace{-20pt}"),
        ("\\vspace{-16pt}", "\\vspace{-20pt}"),
        ("\\vspace{-17pt}", "\\vspace{-22pt}"),
        ("\\vspace{-19pt}", "\\vspace{-22pt}"),
        ("\\vspace{-2 mm}", "\\vspace{-6pt}"),
        ("\\vspace{-4 mm}", "\\vspace{-8pt}"),
        ("\\vspace{-5 mm}", "\\vspace{-10pt}"),
        ("\\vspace{-6 mm}", "\\vspace{-12pt}"),
    ]
    for old, new in replacements:
        tex_content = tex_content.replace(old, new)
    return tex_content


def remove_latex_auxiliary_files(output_dir: Path, jobname: str) -> None:
    """Remove LaTeX auxiliary files (e.g. .aux, .log, .out) from output_dir, keeping only the .pdf."""
    suffixes = (".aux", ".log", ".out", ".fls", ".synctex.gz", ".fdb_latexmk")
    for suf in suffixes:
        p = output_dir / f"{jobname}{suf}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def remove_latex_output_from_tex_dir(tex_dir: Path, jobname: str) -> None:
    """Remove any PDF and auxiliary files for this job from tex/ so only pdf/ holds the output."""
    for suf in (".pdf", ".aux", ".log", ".out", ".fls", ".synctex.gz", ".fdb_latexmk"):
        p = tex_dir / f"{jobname}{suf}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def run(
    job_url: str = None,
    link_path: Path = LINK_FILE,
    info_path: Path = INFO_FILE,
    template_path: Path = TEMPLATE_TEX,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """
    Run the pipeline: one LLM call (info.json + job description + template.tex) → .tex → compile to PDF.
    """
    if not info_path.exists():
        fallback_info = PROJECT_DIR / "json" / "info.json"
        if fallback_info.exists():
            info_path = fallback_info
        else:
            raise FileNotFoundError(f"Info file not found: {info_path}")
    if not job_url:
        resolved_link = _first_existing(link_path, PROJECT_DIR / "link.txt")
        if not resolved_link:
            raise FileNotFoundError(f"Link file not found: {link_path}")
        link_path = resolved_link
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    print("1. Loading job link and fetching description...")
    url = job_url if job_url else load_job_link(link_path)
    job_desc = fetch_job_description(url)
    print("2. Loading info.json and template.tex...")
    user_info = load_user_info(info_path)
    template_content = load_template(template_path)
    name = (user_info.get("personal_info") or {}).get("name") or user_info.get("name") or "Candidate"
    safe_name = re.sub(r"[^\w\s-]", "", str(name)).replace(" ", "_")[:30]
    output_dir.mkdir(parents=True, exist_ok=True)
    TEX_DIR.mkdir(parents=True, exist_ok=True)

    print("3. Step 1 — LLM enhancing content for job and ATS (similar sentence length)...")
    enhanced = llm_enhance_for_job(user_info, job_desc)
    print("4. Step 2 — LLM filling template structure only (headers, lines, margins) with enhanced content...")
    filled_tex = llm_fill_template_structure_only(enhanced, template_content)
    jobname = f"resume_{safe_name}"
    tex_path = TEX_DIR / f"{jobname}.tex"
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(filled_tex)

    print("5. Compiling LaTeX to PDF...")
    filled_tex_current = filled_tex
    max_tighten_attempts = 3
    for attempt in range(max_tighten_attempts):
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(filled_tex_current)
        pdf_path, err_msg = compile_latex_to_pdf(tex_path, output_dir, jobname)
        if not pdf_path:
            if "pdflatex not found" in err_msg.lower():
                print("   pdflatex not found. Returning generated .tex file instead.")
                return tex_path
            raise RuntimeError(f"pdflatex failed.\n{err_msg}")
        pages = get_pdf_page_count_from_log(output_dir, jobname)
        if pages <= 1:
            break
        if attempt < max_tighten_attempts - 1:
            print(f"   PDF has {pages} page(s); tightening spacing to fit one page...")
            filled_tex_current = reduce_tex_spacing(filled_tex_current)
    remove_latex_auxiliary_files(output_dir, jobname)
    remove_latex_output_from_tex_dir(TEX_DIR, jobname)
    print(f"   Done. Resume saved to: {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    try:
        run()
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
