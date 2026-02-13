#!/usr/bin/env python3
"""
relabeledPDFs.py - Rename academic PDF files using metadata extracted from each PDF.

New filename format:
    LastName + Year + First6ContentWordsInCamelCase + .pdf
Example:
    Thompson2022LammpsFlexibleSimulationToolParticleBased.pdf

Metadata extraction strategy (in priority order):
    1. CrossRef API lookup via DOI found in PDF metadata or text
    2. Direct text parsing of the first two pages (via pdftotext CLI)
    3. Fallback text parsing via pypdf (pure Python, no external tools)

Dependencies:
    Required: pypdf   (pip install pypdf)
    Optional: pdftotext CLI from poppler-utils (much better text extraction)
    Optional: pdfplumber (pip install pdfplumber) - alternative text extraction

Usage:
    python relabeledPDFs.py /path/to/pdf/folder              # rename files
    python relabeledPDFs.py /path/to/pdf/folder --dry-run    # preview only
    python relabeledPDFs.py /path/to/pdf/folder --json       # output JSON mapping
    python relabeledPDFs.py /path/to/pdf/folder --verbose    # verbose output
    python relabeledPDFs.py /path/to/pdf/folder --email blaine-mooers@ou.edu    # verbose output
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Stop words to skip when selecting the six title content words
STOP_WORDS = {
    'a', 'an', 'the', 'of', 'for', 'in', 'on', 'at', 'to', 'and', 'or',
    'by', 'with', 'from', 'as', 'is', 'are', 'was', 'were', 'that',
    'this', 'but', 'not', 'via', 'into', 'vs',
}

# Acronyms and terms that should preserve their canonical casing.
# Add domain-specific terms as needed.
PRESERVE_CASE = {
    # Nucleic acids and biology
    'rna': 'RNA', 'dna': 'DNA', 'mrna': 'mRNA', 'mrnas': 'mRNAs',
    'rrna': 'rRNA', 'trna': 'tRNA', 'rnas': 'RNAs',
    'snp': 'SNP', 'snps': 'SNPs', 'pcr': 'PCR',
    # Structural biology
    'nmr': 'NMR', 'pdb': 'PDB', 'xfel': 'XFEL',
    'cryo': 'Cryo', 'cryoem': 'CryoEM',
    'saxs': 'SAXS', 'xray': 'Xray',
    # Drug Discovery
    'qsar': 'QSAR'
    # Dimensions
    '3d': '3D', '2d': '2D', '1d': '1D',
    # Virus / disease
    'sars': 'SARS', 'cov': 'CoV', 'covid': 'COVID',
    'hiv': 'HIV', 'mpro': 'Mpro',
    # Roman numerals
    'ii': 'II', 'iii': 'III', 'iv': 'IV', 'vi': 'VI',
    # Software / databases (extend as needed)
    'emdna': 'emDNA', '3dna': '3DNA', 'g4rna': 'G4RNA',
    'g4catchall': 'G4Catchall', 'vfoldla': 'VfoldLA',
    'rnapolis': 'RNApolis', 'rnapdbee': 'RNApdbee',
    'clarna': 'ClaRNA', 'onquadro': 'ONQUADRO',
    'gaia': 'GAIA', 'qparse': 'QPARSE', 'eltetrado': 'ElTetrado',
    'fr3d': 'FR3D', 'pymod': 'PyMod', 'farfar2': 'FARFAR2',
    'lammps': 'LAMMPS', 'gromacs': 'GROMACS', 'pymol': 'PyMOL',
    'phenix': 'PHENIX', 'coot': 'Coot', 'chimera': 'Chimera',
    'rosetta': 'Rosetta',
    # Compound terms created by merging single-letter hyphen prefixes
    'gquadruplex': 'GQuadruplex', 'gquadruplexes': 'GQuadruplexes',
    'pfarfar2': 'PFARFAR2',
    'g4': 'G4',
    # Compound hyphenated words that get merged
    'longlooped': 'LongLooped',
    'assemblybased': 'AssemblyBased',
    'topologybased': 'TopologyBased',
}

# Contact email for CrossRef API (polite pool).  Change to your own.
_crossref_email = 'user@example.com'


def _get_crossref_email() -> str:
    return _crossref_email


def _set_crossref_email(email: str):
    global _crossref_email
    _crossref_email = email


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _has_pdftotext() -> bool:
    """Check whether the pdftotext CLI (poppler-utils) is available."""
    return shutil.which('pdftotext') is not None


def extract_text_pdftotext(filepath: str, max_pages: int = 2) -> str:
    """Extract text from the first *max_pages* pages using the pdftotext CLI.

    pdftotext (from poppler-utils) generally produces cleaner text than
    pure-Python PDF libraries, especially for multi-column academic layouts.
    """
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', '-l', str(max_pages), filepath, '-'],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout
    except Exception:
        return ''


def extract_text_pypdf(filepath: str, max_pages: int = 2) -> str:
    """Extract text using pypdf (pure Python fallback)."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        text = ''
        for page in reader.pages[:max_pages]:
            t = page.extract_text()
            if t:
                text += t + '\n'
        return text
    except Exception:
        return ''


def extract_text_pdfplumber(filepath: str, max_pages: int = 2) -> str:
    """Extract text using pdfplumber (optional dependency)."""
    try:
        import pdfplumber
        text = ''
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages[:max_pages]:
                t = page.extract_text()
                if t:
                    text += t + '\n'
        return text
    except ImportError:
        return ''
    except Exception:
        return ''


def extract_text(filepath: str, max_pages: int = 2) -> str:
    """Extract text from a PDF using the best available method."""
    if _has_pdftotext():
        text = extract_text_pdftotext(filepath, max_pages)
        if text.strip():
            return text
    text = extract_text_pypdf(filepath, max_pages)
    if text.strip():
        return text
    return extract_text_pdfplumber(filepath, max_pages)


# ---------------------------------------------------------------------------
# PDF metadata via pypdf
# ---------------------------------------------------------------------------

def get_pypdf_metadata(filepath: str) -> dict:
    """Return a dict with title, author, year from embedded PDF metadata."""
    info = {}
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        meta = reader.metadata
        if not meta:
            return info
        if meta.title and len(str(meta.title).strip()) > 3:
            t = str(meta.title).strip()
            # Skip placeholder titles
            if t.lower() not in {'untitled', 'microsoft word', ''}:
                info['title'] = t
        if meta.author:
            info['author'] = str(meta.author).strip()
        # Year from creation/modification dates
        if hasattr(meta, 'creation_date') and meta.creation_date:
            try:
                info['year'] = str(meta.creation_date.year)
            except Exception:
                pass
        if 'year' not in info:
            for key in ['/CreationDate', '/ModDate']:
                if key in meta:
                    m = re.search(r'(19[89]\d|20[0-2]\d)', str(meta[key]))
                    if m:
                        info['year'] = m.group(1)
                        break
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# DOI extraction
# ---------------------------------------------------------------------------

def extract_doi(filepath: str, text: str) -> str | None:
    """Try to find a DOI from PDF metadata, filename, or page text."""
    # 1. Embedded PDF metadata
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        meta = reader.metadata
        if meta:
            for key in ['/doi', '/DOI', '/Subject', '/Keywords']:
                if key in meta and meta[key]:
                    m = re.search(r'(10\.\d{4,9}/[^\s,;]+)', str(meta[key]))
                    if m:
                        return m.group(1).rstrip('.')
            if meta.title:
                m = re.search(r'(10\.\d{4,9}/[^\s,;]+)', str(meta.title))
                if m:
                    return m.group(1).rstrip('.')
    except Exception:
        pass

    # 2. Filename patterns
    fname = os.path.basename(filepath)
    # DOI encoded in filename  e.g. 10.1515_bmc.2011.016.pdf
    m = re.search(r'(10\.\d{4,9})[_/](.+?)\.pdf$', fname)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # 3. Page text
    if text:
        for pat in [
            r'(?:doi|DOI)[:\s]*\s*(10\.\d{4,9}/[^\s,;]+)',
            r'https?://doi\.org/(10\.\d{4,9}/[^\s,;]+)',
            r'https?://dx\.doi\.org/(10\.\d{4,9}/[^\s,;]+)',
            r'(10\.\d{4,9}/[^\s,;]+)',
        ]:
            m = re.search(pat, text[:6000])
            if m:
                doi = m.group(1).rstrip('.)')
                if len(doi) > 10:
                    return doi
    return None


# ---------------------------------------------------------------------------
# CrossRef API lookup
# ---------------------------------------------------------------------------

def lookup_crossref(doi: str) -> dict | None:
    """Query the CrossRef API for metadata associated with *doi*."""
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': f'RelabeledPDFs/1.0 (mailto:{_get_crossref_email()})',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get('message', {})
    except Exception:
        return None


def parse_crossref(cr: dict) -> tuple:
    """Return (author_last, year, title) from a CrossRef work record."""
    if not cr:
        return None, None, None
    # Title
    title = None
    titles = cr.get('title', [])
    if titles:
        title = titles[0]
    # Year
    year = None
    for field in ['published-print', 'published-online', 'issued', 'created']:
        parts = cr.get(field, {}).get('date-parts', [[]])
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    # First author last name
    author = None
    authors = cr.get('author', [])
    if authors:
        author = authors[0].get('family', '')
        if not author:
            name = authors[0].get('name', '')
            if name:
                author = name.split()[-1]
    return author, year, title


# ---------------------------------------------------------------------------
# Text-based metadata extraction (fallback)
# ---------------------------------------------------------------------------

def extract_year_from_text(text: str) -> str | None:
    """Find a plausible publication year in the first ~5 000 characters."""
    for pat in [
        r'(?:©|\(c\)|copyright)\s*(\d{4})',
        r'(?:published|received|accepted|submitted)[:\s]+.*?(\d{4})',
        r'\b(20[0-2]\d|19[89]\d)\b',
    ]:
        m = re.search(pat, text[:5000], re.IGNORECASE)
        if m:
            y = int(m.group(1))
            if 1980 <= y <= 2026:
                return str(y)
    return None


def extract_title_from_text(text: str) -> str | None:
    """Heuristically locate the paper title in the first-page text."""
    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    skip_re = [
        re.compile(r'^(nucleic acids|bioinformatics|journal|volume|vol\.|no\.|'
                   r'pages?|doi|http|www|received|accepted|published|copyright|©'
                   r'|downloaded|open access|research article|original paper'
                   r'|article|review|short communication|letter)',
                   re.IGNORECASE),
        re.compile(r'^\d+[\s.]'),       # page numbers
        re.compile(r'^\w+\s+\d{4}'),    # "Journal 2020" headers
        re.compile(r'^\s*$'),
    ]
    for i, line in enumerate(lines[:25]):
        if len(line) < 12:
            continue
        if any(p.match(line) for p in skip_re):
            continue
        title = line
        # Merge a likely continuation line
        if (i + 1 < len(lines)
                and not line.endswith('.')
                and len(lines[i + 1]) > 10
                and not any(p.match(lines[i + 1]) for p in skip_re)):
            nxt = lines[i + 1]
            if nxt[0].islower() or (not nxt.endswith('.') and len(nxt) > 15):
                title = f"{line} {nxt}"
        return title
    return None


def extract_author_from_text(text: str, title: str | None) -> str | None:
    """Heuristically locate the first author's last name after the title."""
    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    title_seen = False
    for i, line in enumerate(lines[:35]):
        if title and line.startswith((title or '')[:20]):
            title_seen = True
            continue
        if title_seen or i > 5:
            cleaned = re.sub(r'[\d*†‡§¶,]+', ' ', line).strip()
            m = re.match(
                r'^([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z\'-]+)',
                cleaned,
            )
            if m:
                parts = m.group(1).split()
                if len(parts) >= 2:
                    return parts[-1]
    return None


# ---------------------------------------------------------------------------
# CamelCase title conversion
# ---------------------------------------------------------------------------

def title_to_camel(title: str, n: int = 6) -> str:
    """Convert the first *n* content words of *title* to CamelCase.

    Stop words are skipped.  Known acronyms preserve their canonical casing.
    Single-letter hyphen prefixes are merged with the following part so that
    "G-quadruplex" becomes "GQuadruplex" (one word) rather than "G" + "Quadruplex".
    Multi-character hyphenated parts (e.g. "Particle-Based") are split into
    separate words ("Particle" + "Based").
    """
    if not title:
        return ''
    # Strip punctuation except hyphens (handled separately)
    cleaned = re.sub(r'[–—:,;.!?()""\'\"\\\/\[\]{}]', ' ', title)
    raw_words = cleaned.split()

    # Expand / merge hyphenated parts
    words: list[str] = []
    for w in raw_words:
        parts = w.split('-')
        merged: list[str] = []
        idx = 0
        while idx < len(parts):
            p = re.sub(r'[^a-zA-Z0-9]', '', parts[idx])
            if not p:
                idx += 1
                continue
            # Merge single-letter prefix with the next part
            if len(p) == 1 and idx + 1 < len(parts):
                nxt = re.sub(r'[^a-zA-Z0-9]', '', parts[idx + 1])
                if nxt:
                    merged.append(p + nxt)
                    idx += 2
                    continue
            merged.append(p)
            idx += 1
        words.extend(merged)

    # Keep only content words (skip stop words)
    content = [w for w in words if w.lower() not in STOP_WORDS]
    selected = content[:n]

    # Build CamelCase string
    camel = ''
    for w in selected:
        low = w.lower()
        if low in PRESERVE_CASE:
            camel += PRESERVE_CASE[low]
        else:
            camel += (w[0].upper() + w[1:].lower()) if len(w) > 1 else w.upper()
    return camel


# ---------------------------------------------------------------------------
# Author name helpers
# ---------------------------------------------------------------------------

def parse_first_author_last(author_str: str) -> str | None:
    """Extract the first author's last name from a raw author string."""
    if not author_str:
        return None
    author_str = author_str.strip()

    # "Last, First; Last, First" -> first author before semicolon
    if ';' in author_str:
        author_str = author_str.split(';')[0].strip()
    elif ' and ' in author_str.lower():
        author_str = re.split(r'\band\b', author_str, flags=re.IGNORECASE)[0].strip()

    # Remove affiliation markers
    author_str = re.sub(r'[\d*†‡§¶]+$', '', author_str).strip()

    # "Last, First" format
    if ',' in author_str:
        return author_str.split(',')[0].strip().split()[-1]

    parts = author_str.split()
    return parts[-1] if parts else None


# ---------------------------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------------------------

def process_pdf(filepath: str, verbose: bool = False) -> dict:
    """Extract metadata from a single PDF and propose a new filename.

    Returns a dict with keys:
        original, author, year, title, doi, source, new_name, missing
    """
    filename = os.path.basename(filepath)
    entry: dict = {
        'original': filename,
        'author': None,
        'year': None,
        'title': None,
        'doi': None,
        'source': 'none',
        'new_name': None,
        'missing': [],
    }

    # --- Extract page text ---
    text = extract_text(filepath)

    # --- DOI ---
    doi = extract_doi(filepath, text)
    entry['doi'] = doi
    if verbose and doi:
        print(f"  DOI: {doi}")

    author, year, title = None, None, None

    # --- Strategy 1: CrossRef via DOI ---
    if doi:
        time.sleep(0.3)  # polite delay
        cr = lookup_crossref(doi)
        if cr:
            author, year, title = parse_crossref(cr)
            if author and year and title:
                entry['source'] = 'crossref'
                if verbose:
                    print(f"  [CrossRef] {author}, {year}, {title[:72]}…")

    # --- Strategy 2: pypdf embedded metadata ---
    pmeta = get_pypdf_metadata(filepath)
    if not title and pmeta.get('title'):
        title = pmeta['title']
    if not author and pmeta.get('author'):
        author = parse_first_author_last(pmeta['author'])
    if not year and pmeta.get('year'):
        year = pmeta['year']
    if author and year and title and entry['source'] == 'none':
        entry['source'] = 'pypdf'

    # --- Strategy 3: Text parsing ---
    if not title:
        title = extract_title_from_text(text)
    if not author:
        author = extract_author_from_text(text, title)
    if not year:
        year = extract_year_from_text(text)
    if author and year and title and entry['source'] == 'none':
        entry['source'] = 'text'

    entry['author'] = author
    entry['year'] = year
    entry['title'] = title

    # --- Build new filename ---
    if author and year and title:
        clean_author = re.sub(r'[^\w]', '', author)
        camel = title_to_camel(title, 6)
        entry['new_name'] = f"{clean_author}{year}{camel}.pdf"
    else:
        if not author:
            entry['missing'].append('author')
        if not year:
            entry['missing'].append('year')
        if not title:
            entry['missing'].append('title')

    return entry


def process_directory(
    pdf_dir: str,
    dry_run: bool = False,
    as_json: bool = False,
    verbose: bool = False,
) -> list[dict]:
    """Process every PDF in *pdf_dir* and (optionally) rename them."""
    pdf_dir = os.path.abspath(pdf_dir)
    pdf_files = sorted(
        f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')
    )
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return []

    print(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}\n")
    results: list[dict] = []
    seen_names: dict[str, int] = {}

    for idx, fname in enumerate(pdf_files, 1):
        fpath = os.path.join(pdf_dir, fname)
        if not dry_run and not as_json:
            print(f"[{idx}/{len(pdf_files)}] {fname}")

        entry = process_pdf(fpath, verbose=verbose)

        # Deduplicate proposed names
        if entry['new_name']:
            base_name = entry['new_name']
            if base_name in seen_names:
                seen_names[base_name] += 1
                stem = base_name.replace('.pdf', '')
                entry['new_name'] = f"{stem}{seen_names[base_name]}.pdf"
            else:
                seen_names[base_name] = 1

        results.append(entry)

        if not as_json:
            if entry['new_name']:
                print(f"  -> {entry['new_name']}")
            else:
                print(f"  *** NEEDS REVIEW (missing: {', '.join(entry['missing'])})")

    # --- JSON output mode ---
    if as_json:
        # Strip 'missing' key when empty for cleaner output
        clean = []
        for r in results:
            out = {k: v for k, v in r.items() if k != 'missing' or v}
            clean.append(out)
        print(json.dumps(clean, indent=2, ensure_ascii=False))
        return results

    # --- Summary ---
    ok = sum(1 for r in results if r['new_name'])
    fail = sum(1 for r in results if not r['new_name'])
    print(f"\n{'=' * 60}")
    print(f"Ready to rename: {ok}   |   Need manual review: {fail}")

    if dry_run:
        print("(dry-run mode — no files were renamed)")
        return results

    # --- Execute renames ---
    if ok == 0:
        print("Nothing to rename.")
        return results

    renamed = 0
    errors = 0
    for entry in results:
        if not entry['new_name']:
            continue
        old = os.path.join(pdf_dir, entry['original'])
        new = os.path.join(pdf_dir, entry['new_name'])
        if os.path.exists(new):
            print(f"  SKIP (target exists): {entry['new_name']}")
            errors += 1
            continue
        try:
            os.rename(old, new)
            renamed += 1
        except OSError as exc:
            print(f"  ERROR: {entry['original']} -> {exc}")
            errors += 1

    print(f"\nRenamed {renamed} file(s).  Errors: {errors}")
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Rename academic PDF files to '
                    'LastNameYearFirst6TitleWordsCamelCase.pdf',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Directory containing PDF files (default: current directory)',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview renames without actually renaming files',
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        dest='as_json',
        help='Output the mapping as JSON (implies --dry-run)',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed extraction information',
    )
    parser.add_argument(
        '--email',
        default='user@example.com',
        help='Email address for CrossRef polite API pool '
             '(default: %(default)s)',
    )
    args = parser.parse_args()

    _set_crossref_email(args.email)

    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run or args.as_json
    process_directory(
        args.directory,
        dry_run=dry_run,
        as_json=args.as_json,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    main()
