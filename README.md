# Relabel PDFs without Burning up the Planet by Using AI

![Version](https://img.shields.io/static/v1?label=relabel-pdfs&message=0.1&color=brightcolor)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Overview

`relabeledPDFs.py` renames academic PDF files using metadata extracted directly from each PDF.
The new filenames follow a standardized, human-readable convention:

```
FirstAuthorLastName + Year + FirstSixContentWordsInCamelCase.pdf
```

For example, the file `029401_1_online.pdf` becomes:

```
Thompson2022LAMMPSFlexibleSimulationToolParticleBased.pdf
```

This naming convention makes it possible to identify the paper at a glance in a file browser without opening it.

## Problem

Downloaded academic PDFs arrive with opaque filenames: publisher-assigned hashes (`029401_1_online.pdf`), DOI-encoded strings (`10.1515_bmc.2011.016.pdf`), or truncated titles.
Manually renaming dozens or hundreds of papers is tedious, error-prone and time-consumging.
Using AI for all repetitive tasks of this nature is unethical; use scripts instead.
`relabeledPDFs.py` automates the process by extracting author, year, and title metadata from each PDF and constructing a consistent filename.

## How it works

The script uses a three-tier metadata extraction strategy, attempting each in order and stopping at the first success:

1. **CrossRef API lookup** — If a DOI is found (in PDF metadata, the filename, or the page text), the script queries the CrossRef REST API for authoritative metadata.
2. **Embedded PDF metadata (pypdf)** — The script reads the `/Title`, `/Author`, and `/CreationDate` fields stored inside the PDF itself.
3. **Text parsing fallback** — As a last resort, the script extracts the first two pages of text (preferring the `pdftotext` CLI from poppler-utils for its superior handling of multi-column layouts) and applies heuristic regex patterns to locate the title, first author, and publication year.

The CamelCase title conversion applies several domain-aware rules:

- **Stop word filtering**: articles, prepositions, and conjunctions (a, an, the, of, for, in, ...) are skipped so that only content words count toward the six-word limit.
- **Acronym preservation**: a `PRESERVE_CASE` dictionary ensures that terms like RNA, DNA, 3D, LAMMPS, PyMOL, GROMACS, and SARS-CoV-2 retain their canonical casing rather than being lowered to Rna, Dna, Lammps, etc.
- **Single-letter hyphen prefix merging**: "G-quadruplex" becomes `GQuadruplex` (one word), because splitting it would waste one of the six word slots on the single letter "G".
- **Multi-character hyphenated word splitting**: "Particle-Based" becomes `Particle` + `Based` (two separate words).

## Requirements

**Required:**

- Python 3.10 or later
- [pypdf](https://pypi.org/project/pypdf/) (`pip install pypdf`)

**Optional (recommended):**

- `pdftotext` CLI from [poppler-utils](https://poppler.freedesktop.org/) — produces much cleaner text extraction than pure-Python alternatives, especially for multi-column academic paper layouts.
  Install with `brew install poppler` (macOS), `sudo apt install poppler-utils` (Debian/Ubuntu), or `conda install -c conda-forge poppler`.
- [pdfplumber](https://pypi.org/project/pdfplumber/) (`pip install pdfplumber`) — used as a tertiary fallback if both `pdftotext` and pypdf fail to extract usable text.

**For running tests:**

- [pytest](https://pypi.org/project/pytest/) (`pip install pytest`)

## Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/YourUsername/relabeledPDFs.git
cd relabeledPDFs
pip install pypdf pytest
```

Optionally install poppler-utils for improved text extraction:

```bash
# macOS
brew install poppler

# Debian / Ubuntu
sudo apt install poppler-utils

# Conda
conda install -c conda-forge poppler
```

## Usage

### Basic rename

Rename all PDFs in a directory:

```bash
python relabeledPDFs.py /path/to/pdf/folder
```

The script prints a progress log, renames files in place, and reports a summary at the end.

### Dry run (preview without renaming)

Preview the proposed filenames without modifying anything on disk:

```bash
python relabeledPDFs.py /path/to/pdf/folder --dry-run
```

or equivalently:

```bash
python relabeledPDFs.py /path/to/pdf/folder -n
```

Sample output:

```
Found 48 PDF(s) in /Users/blaine/papers

[1/48] 029401_1_online.pdf
  -> Thompson2022LAMMPSFlexibleSimulationToolParticleBased.pdf
[2/48] gkac123.pdf
  -> Zok2022RNApolisStructuralBioinformaticsPlatformRNA.pdf
...

============================================================
Ready to rename: 45   |   Need manual review: 3
(dry-run mode — no files were renamed)
```

### JSON output

Export the full metadata mapping as JSON (useful for scripting or post-processing):

```bash
python relabeledPDFs.py /path/to/pdf/folder --json
```

JSON mode implies `--dry-run`. Redirect the output to a file if desired:

```bash
python relabeledPDFs.py /path/to/pdf/folder --json > rename_map.json
```

### Verbose mode

Print detailed extraction information (DOIs found, CrossRef responses):

```bash
python relabeledPDFs.py /path/to/pdf/folder --dry-run --verbose
```

### Specifying a CrossRef email

The CrossRef API routes requests with a contact email to a faster "polite" pool.
Provide your email for better performance when processing large batches:

```bash
python relabeledPDFs.py /path/to/pdf/folder --email you@university.edu
```

### Combining flags

Flags can be combined freely:

```bash
python relabeledPDFs.py ~/Downloads/papers --dry-run --verbose --email you@university.edu
```

### Default directory

When called without a directory argument, the script processes the current working directory:

```bash
cd /path/to/pdf/folder
python relabeledPDFs.py --dry-run
```

## CLI reference

```
usage: relabeledPDFs.py [-h] [--dry-run] [--json] [--verbose] [--email EMAIL]
                        [directory]

Rename academic PDF files to LastNameYearFirst6TitleWordsCamelCase.pdf

positional arguments:
  directory             Directory containing PDF files (default: current directory)

optional arguments:
  --dry-run, -n         Preview renames without actually renaming files
  --json, -j            Output the mapping as JSON (implies --dry-run)
  --verbose, -v         Print detailed extraction information
  --email EMAIL         Email address for CrossRef polite API pool
                        (default: user@example.com)
```

## Customization

### Adding acronyms

To preserve the casing of additional domain-specific terms, add entries to the `PRESERVE_CASE` dictionary near the top of the script:

```python
PRESERVE_CASE = {
    ...
    'crispr': 'CRISPR',
    'alphafold': 'AlphaFold',
    'openai': 'OpenAI',
}
```

The key must be the all-lowercase form. The value is the canonical casing that will appear in the filename.

### Adding stop words

To skip additional words during title conversion, add them (in lowercase) to the `STOP_WORDS` set:

```python
STOP_WORDS = {
    ...
    'using', 'based', 'toward',
}
```

### Changing the word count

The default of six content words can be changed globally by modifying the `n=6` default in the `title_to_camel()` function signature, or on a per-call basis:

```python
camel = title_to_camel("Some Very Long Title ...", n=8)
```

## Test suite

The file `test_relabeledPDFs.py` contains 95 tests organized into unit tests and integration tests.
Run the full suite with:

```bash
pytest test_relabeledPDFs.py -v
```

or:

```bash
python -m pytest test_relabeledPDFs.py -v --tb=short
```

All 95 tests pass in approximately 0.3 seconds.

### Test organization

The tests are grouped into 15 classes covering every public function.
The table below summarizes the class, the function or feature it targets, and the count of test methods.

| Test class | Target function / feature | Tests | Type |
|:---|:---|:---:|:---|
| `TestTitleToCamel` | `title_to_camel()` — stop words, acronyms, hyphens, punctuation, word count, case | 23 | Unit |
| `TestParseFirstAuthorLast` | `parse_first_author_last()` — name formats, separators, edge cases | 10 | Unit |
| `TestExtractYearFromText` | `extract_year_from_text()` — copyright, published/accepted, range boundaries | 9 | Unit |
| `TestExtractTitleFromText` | `extract_title_from_text()` — header skipping, continuation lines | 5 | Unit |
| `TestExtractAuthorFromText` | `extract_author_from_text()` — author line detection | 2 | Unit |
| `TestParseCrossref` | `parse_crossref()` — complete records, date fallbacks, corporate authors | 7 | Unit |
| `TestExtractDoi` | `extract_doi()` — doi: prefix, URLs, filenames, bare DOIs | 7 | Unit |
| `TestCrossrefEmailAccessors` | `_get/_set_crossref_email()` | 2 | Unit |
| `TestLookupCrossref` | `lookup_crossref()` — mocked HTTP success and failure | 4 | Unit |
| `TestHasPdftotext` | `_has_pdftotext()` — mocked `shutil.which` | 2 | Unit |
| `TestExtractText` | `extract_text()` — fallback chain (pdftotext → pypdf → pdfplumber) | 3 | Unit |
| `TestProcessPdfWithMock` | `process_pdf()` — CrossRef, pypdf, text, missing-metadata paths | 4 | Integration |
| `TestProcessDirectoryIntegration` | `process_directory()` — dry run, JSON, rename, dedup, skip, empty dir | 6 | Integration |
| `TestMainCLI` | `main()` — argparse flags, exit codes | 3 | Integration |
| `TestEdgeCases` | Boundary conditions, unicode, slashes, dictionary completeness | 8 | Edge case |

### What the unit tests verify

Each unit test class isolates a single function and feeds it controlled inputs.
External dependencies (network, file system, subprocess calls) are replaced with `unittest.mock` patches so that the tests run without network access, without PDF files on disk, and without poppler-utils installed.

Key areas of coverage:

- **CamelCase conversion** (`TestTitleToCamel`): The largest test class, with 23 tests, because the naming logic is the heart of the script. Tests verify that stop words are skipped, that acronyms like RNA, DNA, 3D, LAMMPS, PyMOL, and SARS-CoV-2 retain canonical casing, that single-letter hyphen prefixes merge correctly (G-quadruplex → GQuadruplex), that multi-character hyphenated words split into separate word slots, that exactly six content words are selected, that punctuation (colons, em-dashes, parentheses) is stripped, and that empty or `None` inputs return empty strings.
- **Author parsing** (`TestParseFirstAuthorLast`): Covers "First Last", "Last, First", semicolon-separated lists, "and"-separated lists, affiliation marker stripping (†, ‡, superscript digits), compound last names (Garcia-Lopez), single corporate names (Formulatrix), and middle initials.
- **Year extraction** (`TestExtractYearFromText`): Exercises the priority order of regex patterns (copyright © first, then published/received/accepted keywords, then bare four-digit years) and verifies that years before 1980 or after 2026 are rejected.
- **DOI extraction** (`TestExtractDoi`): Tests DOIs found via `doi:` prefix, `https://doi.org/` URLs, `https://dx.doi.org/` URLs, filename-encoded DOIs (e.g., `10.1515_bmc.2011.016.pdf`), bare DOIs in body text, and trailing period stripping.
- **CrossRef parsing** (`TestParseCrossref`): Feeds mock CrossRef JSON records with different date field combinations (`published-print`, `published-online`, `issued`) and author field formats (`family` vs. `name`) to verify the fallback chain.
- **Text extraction fallback** (`TestExtractText`): Mocks the three extraction backends to confirm that `pdftotext` is preferred when available, that `pypdf` is used when `pdftotext` is absent or returns empty text, and that `pdfplumber` is the last resort.

### What the integration tests verify

Integration tests create real (minimal) PDF files in a temporary directory using `pypdf.PdfWriter`, then call `process_pdf()` or `process_directory()` and verify observable outcomes:

- **Dry-run preservation**: The file listing before and after a `--dry-run` invocation is identical — no files are renamed, created, or deleted.
- **JSON output**: The `--json` flag produces valid JSON that `json.loads()` can parse, with one entry per PDF.
- **Actual rename**: After a non-dry-run invocation, PDFs with extractable metadata are renamed to the new filenames and the original filenames no longer exist.
- **Deduplication**: When two PDFs would receive the same proposed filename, the second one gets a numeric suffix (e.g., `Smith2023TestPaper2.pdf`).
- **Target-exists skip**: If the proposed target filename already exists on disk, the rename is skipped rather than overwriting.
- **Empty directory**: Processing a directory with no PDFs prints a message and returns an empty list without errors.
- **CLI flags**: The `--dry-run`, `--json`, `--verbose`, and `--email` flags are accepted by argparse. A nonexistent directory argument causes `sys.exit(1)`.
- **Metadata source priority**: With mocked extraction functions, the tests verify that CrossRef results take priority over pypdf metadata, which in turn takes priority over heuristic text parsing.

### Running a subset of tests

Run only the CamelCase tests:

```bash
pytest test_relabeledPDFs.py -k "TestTitleToCamel" -v
```

Run only the integration tests:

```bash
pytest test_relabeledPDFs.py -k "Integration or MainCLI or ProcessPdf" -v
```

Run a single test by name:

```bash
pytest test_relabeledPDFs.py::TestTitleToCamel::test_sars_cov_preserved -v
```

## Project structure

```
relabeledPDFs/
├── relabeledPDFs.py         # Main script
├── test_relabeledPDFs.py    # Unit and integration tests (95 tests)
└── README.md                # This file
```

## Limitations

- **Text extraction quality varies**: Some PDFs (scanned images, heavily formatted layouts, encrypted files) may yield poor text extraction, causing the heuristic fallbacks to produce incorrect metadata. Use `--dry-run` to review before committing.
- **CrossRef API requires network access**: The best metadata source depends on an internet connection and a DOI being present in the PDF.
- **Heuristic author/title detection**: The text-based fallback uses regex patterns tuned for common academic paper layouts. Unusual formatting (e.g., titles in images, authors in footers) may not be detected.
- **Six-word limit**: Extremely long titles may lose distinguishing information. Increase `n` in `title_to_camel()` if this is a concern.

## Status 

Alpha. 
Does not handle all edge cases yet. 
The lead author's last name is sometime is somethings misindentified. 
Some manul editing is still required.

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/improved-parsing`).
3. Add tests for any new functionality.
4. Run `pytest test_relabeledPDFs.py -v` and confirm all tests pass.
5. Submit a pull request.

## Update history

| Version      | Changes                                                                                                                                  | Date                 |
|:-------------|:-----------------------------------------------------------------------------------------------------------------------------------------|:---------------------|
| Version 0.1  | Added badges, funding, and update table. Initial commit.                                                                                 | 2026 February 12     |

## Sources of funding

- NIH: R01 CA242845.
- NIH: R01 AI088011.
- NIH: P30 CA225520 (PI: R. Mannel).
- NIH: P20 GM103640 and P30 GM145423 (PI: A. West).
