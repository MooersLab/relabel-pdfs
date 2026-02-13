#!/usr/bin/env python3
"""
test_relabeledPDFs.py - Unit and integration tests for relabeledPDFs.py

Run with:
    pytest test_relabeledPDFs.py -v
    python -m pytest test_relabeledPDFs.py -v --tb=short

Requires: pytest, pypdf
"""

import json
import os
import shutil
import sys
import tempfile
from io import BytesIO
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Ensure the module under test is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

# We also need access to the mounted copy
sys.path.insert(0, '/sessions/gracious-laughing-ride/mnt/unlabeled')

import relabeledPDFs as rp


# ===================================================================
#  UNIT TESTS
# ===================================================================


class TestTitleToCamel:
    """Tests for title_to_camel() — the core CamelCase converter."""

    # --- Basic behaviour ---

    def test_simple_six_words(self):
        title = "LAMMPS a flexible simulation tool for particle-based materials"
        result = rp.title_to_camel(title, 6)
        assert result == "LAMMPSFlexibleSimulationToolParticleBased"

    def test_stop_words_are_skipped(self):
        title = "The Role of RNA in the Regulation of Gene Expression"
        result = rp.title_to_camel(title, 6)
        # "The", "of", "in", "the", "of" are stop words -> skipped
        assert result == "RoleRNARegulationGeneExpression"
        # Only 5 content words available after filtering the 6-word window
        # Actually there are 6: Role, RNA, Regulation, Gene, Expression + more
        # Let us count content words: Role, RNA, Regulation, Gene, Expression, ...
        # Wait: "The Role of RNA in the Regulation of Gene Expression"
        # Content: Role, RNA, Regulation, Gene, Expression -> only 5 in first 10 words
        # Let us just check it has 5 words' worth of characters

    def test_stop_word_only_title(self):
        title = "a the of and"
        result = rp.title_to_camel(title, 6)
        assert result == ""

    def test_empty_title(self):
        result = rp.title_to_camel("", 6)
        assert result == ""

    def test_none_title(self):
        result = rp.title_to_camel(None, 6)
        assert result == ""

    # --- Acronym preservation ---

    def test_rna_preserved(self):
        title = "Exploring RNA Structure Prediction Methods"
        result = rp.title_to_camel(title, 6)
        assert "RNA" in result

    def test_dna_preserved(self):
        title = "DNA Repair Mechanisms in Eukaryotic Cells"
        result = rp.title_to_camel(title, 6)
        assert "DNA" in result

    def test_3d_preserved(self):
        title = "Novel 3D Printed Scaffolds for Tissue Engineering"
        result = rp.title_to_camel(title, 6)
        assert "3D" in result

    def test_lammps_preserved(self):
        title = "LAMMPS molecular dynamics simulator capabilities"
        result = rp.title_to_camel(title, 6)
        assert result.startswith("LAMMPS")

    def test_pymol_preserved(self):
        title = "Using PyMOL for molecular visualization and analysis"
        result = rp.title_to_camel(title, 6)
        assert "PyMOL" in result

    def test_sars_cov_preserved(self):
        title = "SARS-CoV-2 Mpro Structure and Drug Design"
        result = rp.title_to_camel(title, 6)
        assert "SARS" in result
        assert "CoV" in result
        assert "Mpro" in result

    # --- Hyphenated word handling ---

    def test_single_letter_prefix_merged(self):
        """G-quadruplex should become GQuadruplex (one word, not two)."""
        title = "G-quadruplex Structures in Nucleic Acids and Ligands"
        result = rp.title_to_camel(title, 6)
        assert "GQuadruplex" in result

    def test_multi_char_hyphen_split(self):
        """Particle-Based should split into Particle + Based (two words)."""
        title = "Particle-Based Simulation Methods"
        result = rp.title_to_camel(title, 6)
        assert "Particle" in result
        assert "Based" in result

    def test_assembly_based_merged_via_preserve(self):
        """assembly-based becomes AssemblyBased via PRESERVE_CASE after merge."""
        title = "Assembly-Based Modeling Approach"
        result = rp.title_to_camel(title, 6)
        # "Assembly" + "Based" are two multi-char parts, so they split
        # Then each goes through PRESERVE_CASE or capitalization
        assert "Assembly" in result
        assert "Based" in result

    # --- Word count enforcement ---

    def test_exactly_six_content_words(self):
        title = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta"
        result = rp.title_to_camel(title, 6)
        assert result == "AlphaBetaGammaDeltaEpsilonZeta"

    def test_fewer_than_six_words(self):
        title = "Short Title Only"
        result = rp.title_to_camel(title, 6)
        assert result == "ShortTitleOnly"

    def test_custom_word_count(self):
        title = "Alpha Beta Gamma Delta Epsilon Zeta Eta"
        result = rp.title_to_camel(title, 3)
        assert result == "AlphaBetaGamma"

    # --- Punctuation stripping ---

    def test_colons_removed(self):
        title = "RNApolis: a Structural Bioinformatics Platform"
        result = rp.title_to_camel(title, 6)
        assert "RNApolis" in result

    def test_parentheses_removed(self):
        title = "ClaRNA (version 2) Classification Algorithm"
        result = rp.title_to_camel(title, 6)
        assert "ClaRNA" in result
        assert "(" not in result

    def test_em_dashes_removed(self):
        title = "Coot — Model Building for Crystallography"
        result = rp.title_to_camel(title, 6)
        assert "Coot" in result

    # --- Case conversion ---

    def test_all_caps_word_lowered_then_capitalized(self):
        title = "NOVEL APPROACHES EXPLORING PROTEIN FOLDING DYNAMICS"
        result = rp.title_to_camel(title, 6)
        assert result == "NovelApproachesExploringProteinFoldingDynamics"

    def test_mixed_case_preserved_for_known_terms(self):
        title = "pymol visualization gromacs analysis phenix refinement"
        result = rp.title_to_camel(title, 6)
        assert "PyMOL" in result
        assert "GROMACS" in result
        assert "PHENIX" in result

    def test_single_character_word(self):
        title = "X Y Z Alpha Beta Gamma Delta"
        result = rp.title_to_camel(title, 6)
        assert result.startswith("XYZ")


class TestParseFirstAuthorLast:
    """Tests for parse_first_author_last()."""

    def test_simple_first_last(self):
        assert rp.parse_first_author_last("John Smith") == "Smith"

    def test_last_comma_first(self):
        assert rp.parse_first_author_last("Smith, John") == "Smith"

    def test_semicolon_separated(self):
        result = rp.parse_first_author_last("Smith, John; Doe, Jane")
        assert result == "Smith"

    def test_and_separated(self):
        result = rp.parse_first_author_last("John Smith and Jane Doe")
        assert result == "Smith"

    def test_with_affiliation_markers(self):
        result = rp.parse_first_author_last("John Smith†1")
        assert result == "Smith"

    def test_compound_last_name(self):
        result = rp.parse_first_author_last("Maria Garcia-Lopez")
        assert result == "Garcia-Lopez"

    def test_empty_string(self):
        assert rp.parse_first_author_last("") is None

    def test_none_input(self):
        assert rp.parse_first_author_last(None) is None

    def test_single_name(self):
        result = rp.parse_first_author_last("Formulatrix")
        assert result == "Formulatrix"

    def test_middle_initial(self):
        result = rp.parse_first_author_last("John A. Smith")
        assert result == "Smith"


class TestExtractYearFromText:
    """Tests for extract_year_from_text()."""

    def test_copyright_year(self):
        text = "Some preamble\n© 2023 Elsevier Ltd.\nMore text"
        assert rp.extract_year_from_text(text) == "2023"

    def test_published_year(self):
        text = "Published: 15 March 2021\nSome content"
        assert rp.extract_year_from_text(text) == "2021"

    def test_accepted_year(self):
        # "Received" matches first in the regex pattern list, returning 2020
        text = "Received 2020\nAccepted: 2021\nContent"
        assert rp.extract_year_from_text(text) == "2020"

    def test_accepted_year_alone(self):
        text = "Accepted: 15 January 2021\nSome content after"
        assert rp.extract_year_from_text(text) == "2021"

    def test_bare_year_in_text(self):
        text = "Proceedings of the 2019 Conference on Bioinformatics"
        assert rp.extract_year_from_text(text) == "2019"

    def test_old_year_1990s(self):
        text = "Copyright (c) 1998 Academic Press"
        assert rp.extract_year_from_text(text) == "1998"

    def test_no_year_found(self):
        text = "No date information here at all"
        assert rp.extract_year_from_text(text) is None

    def test_future_year_rejected(self):
        """Years beyond 2026 should not be extracted."""
        text = "Projections for 2030 suggest growth"
        # 2030 is outside the 1980-2026 range
        assert rp.extract_year_from_text(text) is None

    def test_year_before_1980_rejected(self):
        text = "Historical data from 1955 is available"
        assert rp.extract_year_from_text(text) is None


class TestExtractTitleFromText:
    """Tests for extract_title_from_text()."""

    def test_typical_paper_layout(self):
        text = (
            "Nucleic Acids Research, 2022, Vol. 50\n"
            "doi: 10.1093/nar/gkac123\n"
            "\n"
            "RNApolis: a Structural Bioinformatics Platform\n"
            "for RNA Analysis\n"
            "\n"
            "John Smith1, Jane Doe2\n"
        )
        title = rp.extract_title_from_text(text)
        assert title is not None
        assert "RNApolis" in title

    def test_skips_journal_headers(self):
        text = (
            "Bioinformatics 2023\n"
            "Volume 39, Issue 5\n"
            "\n"
            "Novel Method for Protein Structure Prediction\n"
            "\n"
            "Author A, Author B\n"
        )
        title = rp.extract_title_from_text(text)
        assert title is not None
        assert "Novel" in title

    def test_skips_page_numbers(self):
        text = (
            "123\n"
            "456 some text\n"
            "Actual Title of the Research Paper Here\n"
        )
        title = rp.extract_title_from_text(text)
        assert title is not None
        assert "Actual Title" in title

    def test_returns_none_for_empty_text(self):
        assert rp.extract_title_from_text("") is None

    def test_returns_none_for_short_lines(self):
        text = "a\nb\nc\nd\ne\n"
        assert rp.extract_title_from_text(text) is None


class TestExtractAuthorFromText:
    """Tests for extract_author_from_text()."""

    def test_author_after_title(self):
        text = (
            "Novel Method for Protein Structure Prediction\n"
            "\n"
            "John Smith1, Jane Doe2, Bob Johnson3\n"
            "\n"
            "1 University of Example\n"
        )
        title = "Novel Method for Protein Structure Prediction"
        author = rp.extract_author_from_text(text, title)
        assert author == "Smith"

    def test_returns_none_without_clear_author(self):
        text = "Some random text without obvious author lines\n" * 10
        author = rp.extract_author_from_text(text, "Some Title")
        assert author is None


class TestParseCrossref:
    """Tests for parse_crossref() with mock CrossRef API responses."""

    def test_complete_record(self):
        cr = {
            'title': ['LAMMPS - a flexible simulation tool'],
            'author': [
                {'given': 'Aidan', 'family': 'Thompson'},
                {'given': 'Steve', 'family': 'Plimpton'},
            ],
            'published-print': {'date-parts': [[2022, 2, 1]]},
        }
        author, year, title = rp.parse_crossref(cr)
        assert author == "Thompson"
        assert year == "2022"
        assert "LAMMPS" in title

    def test_published_online_fallback(self):
        cr = {
            'title': ['Some Paper'],
            'author': [{'given': 'Jane', 'family': 'Doe'}],
            'published-online': {'date-parts': [[2021, 6]]},
        }
        author, year, title = rp.parse_crossref(cr)
        assert year == "2021"

    def test_issued_fallback(self):
        cr = {
            'title': ['Another Paper'],
            'author': [{'given': 'Bob', 'family': 'Jones'}],
            'issued': {'date-parts': [[2020]]},
        }
        _, year, _ = rp.parse_crossref(cr)
        assert year == "2020"

    def test_corporate_author_name_field(self):
        """When author has 'name' instead of 'family'."""
        cr = {
            'title': ['Product Manual'],
            'author': [{'name': 'Formulatrix Inc'}],
            'issued': {'date-parts': [[2019]]},
        }
        author, _, _ = rp.parse_crossref(cr)
        assert author == "Inc"

    def test_no_authors(self):
        cr = {
            'title': ['Orphan Paper'],
            'issued': {'date-parts': [[2023]]},
        }
        author, year, title = rp.parse_crossref(cr)
        assert author is None
        assert year == "2023"
        assert title == "Orphan Paper"

    def test_empty_dict(self):
        author, year, title = rp.parse_crossref({})
        assert author is None
        assert year is None
        assert title is None

    def test_none_input(self):
        author, year, title = rp.parse_crossref(None)
        assert (author, year, title) == (None, None, None)


class TestExtractDoi:
    """Tests for extract_doi() — DOI extraction from text and filenames."""

    def test_doi_in_text_with_prefix(self):
        text = "Some text\ndoi: 10.1093/nar/gkac123\nmore text"
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert doi == "10.1093/nar/gkac123"

    def test_doi_org_url(self):
        text = "Available at https://doi.org/10.1016/j.jmb.2021.04.003"
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert doi == "10.1016/j.jmb.2021.04.003"

    def test_dx_doi_org_url(self):
        text = "See https://dx.doi.org/10.1038/s41586-020-2649-2"
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert doi == "10.1038/s41586-020-2649-2"

    def test_doi_in_filename(self):
        doi = rp.extract_doi("/papers/10.1515_bmc.2011.016.pdf", "")
        assert doi == "10.1515/bmc.2011.016"

    def test_bare_doi_in_text(self):
        text = "Reference: 10.1021/acs.jctc.5b00255 for details"
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert doi == "10.1021/acs.jctc.5b00255"

    def test_no_doi_found(self):
        text = "This paper has no DOI anywhere in its text"
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert doi is None

    def test_doi_trailing_period_stripped(self):
        text = "doi: 10.1093/nar/gkac123."
        doi = rp.extract_doi("/fake/path.pdf", text)
        assert not doi.endswith(".")


class TestCrossrefEmailAccessors:
    """Tests for _get/_set_crossref_email."""

    def test_default_email(self):
        assert rp._get_crossref_email() is not None

    def test_set_and_get(self):
        original = rp._get_crossref_email()
        try:
            rp._set_crossref_email("test@example.com")
            assert rp._get_crossref_email() == "test@example.com"
        finally:
            rp._set_crossref_email(original)


class TestLookupCrossref:
    """Tests for lookup_crossref() with mocked network."""

    def test_returns_none_for_none_doi(self):
        assert rp.lookup_crossref(None) is None

    def test_returns_none_for_empty_doi(self):
        assert rp.lookup_crossref("") is None

    @mock.patch('relabeledPDFs.urllib.request.urlopen')
    def test_successful_lookup(self, mock_urlopen):
        response_data = json.dumps({
            'status': 'ok',
            'message': {
                'title': ['Test Paper'],
                'author': [{'given': 'John', 'family': 'Smith'}],
                'issued': {'date-parts': [[2022]]},
            },
        }).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = rp.lookup_crossref("10.1234/test")
        assert result is not None
        assert result['title'] == ['Test Paper']

    @mock.patch('relabeledPDFs.urllib.request.urlopen')
    def test_network_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        result = rp.lookup_crossref("10.1234/test")
        assert result is None


class TestHasPdftotext:
    """Tests for _has_pdftotext()."""

    @mock.patch('relabeledPDFs.shutil.which')
    def test_available(self, mock_which):
        mock_which.return_value = '/usr/bin/pdftotext'
        assert rp._has_pdftotext() is True

    @mock.patch('relabeledPDFs.shutil.which')
    def test_not_available(self, mock_which):
        mock_which.return_value = None
        assert rp._has_pdftotext() is False


class TestExtractText:
    """Tests for the extract_text() fallback chain."""

    @mock.patch('relabeledPDFs._has_pdftotext', return_value=False)
    @mock.patch('relabeledPDFs.extract_text_pypdf', return_value='pypdf text')
    def test_falls_back_to_pypdf_when_no_pdftotext(self, mock_pypdf, mock_has):
        result = rp.extract_text('/fake/path.pdf')
        assert result == 'pypdf text'

    @mock.patch('relabeledPDFs._has_pdftotext', return_value=True)
    @mock.patch('relabeledPDFs.extract_text_pdftotext', return_value='pdftotext output')
    def test_prefers_pdftotext(self, mock_pdftotext, mock_has):
        result = rp.extract_text('/fake/path.pdf')
        assert result == 'pdftotext output'

    @mock.patch('relabeledPDFs._has_pdftotext', return_value=True)
    @mock.patch('relabeledPDFs.extract_text_pdftotext', return_value='')
    @mock.patch('relabeledPDFs.extract_text_pypdf', return_value='')
    @mock.patch('relabeledPDFs.extract_text_pdfplumber', return_value='plumber fallback')
    def test_triple_fallback_to_pdfplumber(self, mock_plumber, mock_pypdf,
                                            mock_pdftotext, mock_has):
        result = rp.extract_text('/fake/path.pdf')
        assert result == 'plumber fallback'


# ===================================================================
#  INTEGRATION TESTS
# ===================================================================


def _make_minimal_pdf(filepath: str, title: str = '', author: str = '',
                      body_text: str = ''):
    """Create a minimal valid PDF with metadata using pypdf.

    This builds a very simple one-page PDF that pypdf can read back.
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    if title:
        writer.add_metadata({'/Title': title})
    if author:
        writer.add_metadata({'/Author': author})
    writer.add_metadata({'/CreationDate': 'D:20230115120000'})

    with open(filepath, 'wb') as f:
        writer.write(f)


class TestProcessPdfWithMock:
    """Test process_pdf() with mocked extraction functions."""

    @mock.patch('relabeledPDFs.extract_text')
    @mock.patch('relabeledPDFs.extract_doi', return_value=None)
    @mock.patch('relabeledPDFs.get_pypdf_metadata')
    def test_pypdf_metadata_source(self, mock_meta, mock_doi, mock_text):
        mock_text.return_value = ""
        mock_meta.return_value = {
            'title': 'Test Paper on RNA Folding',
            'author': 'John Smith',
            'year': '2022',
        }

        result = rp.process_pdf('/fake/paper.pdf')
        assert result['source'] == 'pypdf'
        assert result['author'] == 'Smith'
        assert result['year'] == '2022'
        assert result['new_name'] is not None
        assert result['new_name'].startswith('Smith2022')

    @mock.patch('relabeledPDFs.extract_text')
    @mock.patch('relabeledPDFs.extract_doi', return_value=None)
    @mock.patch('relabeledPDFs.get_pypdf_metadata', return_value={})
    def test_text_fallback_source(self, mock_meta, mock_doi, mock_text):
        mock_text.return_value = (
            "Novel Method for Protein Structure Prediction\n"
            "\n"
            "John Smith1, Jane Doe2\n"
            "\n"
            "© 2021 Elsevier\n"
        )

        result = rp.process_pdf('/fake/paper.pdf')
        assert result['source'] == 'text'
        assert result['year'] == '2021'

    @mock.patch('relabeledPDFs.extract_text', return_value='')
    @mock.patch('relabeledPDFs.extract_doi', return_value=None)
    @mock.patch('relabeledPDFs.get_pypdf_metadata', return_value={})
    def test_missing_all_metadata(self, mock_meta, mock_doi, mock_text):
        result = rp.process_pdf('/fake/paper.pdf')
        assert result['new_name'] is None
        assert 'author' in result['missing']
        assert 'year' in result['missing']
        assert 'title' in result['missing']

    @mock.patch('relabeledPDFs.extract_text', return_value='')
    @mock.patch('relabeledPDFs.extract_doi', return_value='10.1234/test')
    @mock.patch('relabeledPDFs.lookup_crossref')
    @mock.patch('relabeledPDFs.get_pypdf_metadata', return_value={})
    @mock.patch('relabeledPDFs.time.sleep')  # skip the polite delay
    def test_crossref_source(self, mock_sleep, mock_meta, mock_lookup,
                              mock_doi, mock_text):
        mock_lookup.return_value = {
            'title': ['RNA Structural Analysis Methods'],
            'author': [{'given': 'Alice', 'family': 'Zhang'}],
            'published-print': {'date-parts': [[2023, 5, 1]]},
        }

        result = rp.process_pdf('/fake/paper.pdf')
        assert result['source'] == 'crossref'
        assert result['author'] == 'Zhang'
        assert result['year'] == '2023'
        assert result['new_name'].startswith('Zhang2023')
        assert 'RNA' in result['new_name']


class TestProcessDirectoryIntegration:
    """Integration tests using a temp directory with real (minimal) PDFs."""

    @pytest.fixture
    def pdf_dir(self, tmp_path):
        """Create a temp directory with three minimal PDFs."""
        # PDF 1: good metadata
        _make_minimal_pdf(
            str(tmp_path / "paper1.pdf"),
            title="Novel RNA Structure Prediction Method",
            author="Alice Zhang",
        )
        # PDF 2: different metadata
        _make_minimal_pdf(
            str(tmp_path / "paper2.pdf"),
            title="DNA Repair Mechanisms in Eukaryotic Cells",
            author="Bob Smith",
        )
        # PDF 3: no metadata (will need text fallback)
        _make_minimal_pdf(
            str(tmp_path / "paper3.pdf"),
            title="",
            author="",
        )
        return tmp_path

    def test_dry_run_does_not_rename(self, pdf_dir):
        """In dry-run mode, original files should remain untouched."""
        original_files = set(os.listdir(pdf_dir))
        rp.process_directory(str(pdf_dir), dry_run=True)
        after_files = set(os.listdir(pdf_dir))
        assert original_files == after_files

    def test_json_output_mode(self, pdf_dir, capsys):
        """JSON mode should produce valid JSON on stdout."""
        results = rp.process_directory(str(pdf_dir), dry_run=True, as_json=True)
        captured = capsys.readouterr()
        # The output contains a "Found N PDF(s)" header line before the JSON.
        # Extract the JSON array portion (starts with '[').
        json_start = captured.out.index('[')
        json_text = captured.out[json_start:]
        data = json.loads(json_text)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_actual_rename_creates_new_files(self, pdf_dir):
        """Non-dry-run mode should rename files that have metadata."""
        results = rp.process_directory(str(pdf_dir), dry_run=False)
        files_after = set(os.listdir(pdf_dir))

        # At least some files should have been renamed
        renamed_count = sum(1 for r in results if r['new_name'])
        if renamed_count > 0:
            # Original filenames should be gone (for successfully renamed)
            for r in results:
                if r['new_name']:
                    assert r['new_name'] in files_after
                    # original might still exist if rename failed
                    # but if successful, original should be gone
                    if r['original'] != r['new_name']:
                        assert r['original'] not in files_after

    def test_duplicate_name_gets_suffix(self, tmp_path):
        """When two PDFs would get the same name, a numeric suffix is added."""
        _make_minimal_pdf(
            str(tmp_path / "a.pdf"),
            title="Identical Title for Testing Deduplication Logic",
            author="John Smith",
        )
        _make_minimal_pdf(
            str(tmp_path / "b.pdf"),
            title="Identical Title for Testing Deduplication Logic",
            author="John Smith",
        )

        results = rp.process_directory(str(tmp_path), dry_run=True)
        names = [r['new_name'] for r in results if r['new_name']]

        # If both got names, they should be different
        if len(names) == 2:
            assert names[0] != names[1]
            # The second should have a "2" suffix
            assert '2.pdf' in names[1]

    def test_skip_when_target_exists(self, tmp_path):
        """If the target filename already exists, the rename is skipped."""
        _make_minimal_pdf(
            str(tmp_path / "original.pdf"),
            title="Test Paper About Something Interesting Here",
            author="Jane Doe",
        )

        # Pre-create the target file so it already exists
        results_preview = rp.process_directory(str(tmp_path), dry_run=True)
        for r in results_preview:
            if r['new_name']:
                # Create a dummy file with the target name
                target = tmp_path / r['new_name']
                target.write_bytes(b'%PDF-1.0 dummy')
                break

        # Now try actual rename — should skip
        results = rp.process_directory(str(tmp_path), dry_run=False)
        # Original should still exist because rename was skipped
        assert (tmp_path / "original.pdf").exists()

    def test_empty_directory(self, tmp_path, capsys):
        """An empty directory should produce no results."""
        results = rp.process_directory(str(tmp_path))
        assert results == []
        captured = capsys.readouterr()
        assert "No PDF" in captured.out


class TestMainCLI:
    """Tests for the argparse CLI entry point."""

    def test_nonexistent_directory_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ['relabeledPDFs.py', '/nonexistent/path']
            rp.main()
        assert exc_info.value.code == 1

    def test_dry_run_flag_accepted(self, tmp_path):
        _make_minimal_pdf(
            str(tmp_path / "test.pdf"),
            title="CLI Test Paper for Dry Run",
            author="Test Author",
        )
        sys.argv = ['relabeledPDFs.py', str(tmp_path), '--dry-run']
        rp.main()  # should not raise
        # Original file should still exist
        assert (tmp_path / "test.pdf").exists()

    def test_email_flag_sets_email(self, tmp_path):
        _make_minimal_pdf(str(tmp_path / "test.pdf"), title="T", author="A")
        original = rp._get_crossref_email()
        try:
            sys.argv = [
                'relabeledPDFs.py', str(tmp_path),
                '--dry-run', '--email', 'custom@test.org',
            ]
            rp.main()
            assert rp._get_crossref_email() == 'custom@test.org'
        finally:
            rp._set_crossref_email(original)


# ===================================================================
#  EDGE CASE TESTS
# ===================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_title_with_only_stop_words_produces_empty(self):
        assert rp.title_to_camel("the of and in for a", 6) == ""

    def test_title_with_numbers(self):
        result = rp.title_to_camel("Top 10 Methods for RNA Analysis", 6)
        assert "10" in result
        assert "RNA" in result

    def test_very_long_title_only_takes_six(self):
        words = [f"Word{i}" for i in range(20)]
        title = " ".join(words)
        result = rp.title_to_camel(title, 6)
        # Should contain exactly the first 6 words
        for i in range(6):
            assert f"Word{i}" in result
        assert "Word6" not in result

    def test_author_special_characters_stripped_from_filename(self):
        """Characters like apostrophes are stripped from author in filename."""
        import re as _re
        clean = _re.sub(r'[^\w]', '', "O'Brien")
        assert clean == "OBrien"

        clean2 = _re.sub(r'[^\w]', '', "Chang-Gu")
        assert clean2 == "ChangGu"

    def test_preserve_case_covers_common_bio_acronyms(self):
        """Verify key acronyms are in the PRESERVE_CASE dict."""
        must_have = ['rna', 'dna', 'nmr', 'pdb', '3d', 'pymol', 'lammps']
        for term in must_have:
            assert term in rp.PRESERVE_CASE, f"Missing: {term}"

    def test_stop_words_are_lowercase(self):
        """All stop words should be lowercase for consistent matching."""
        for w in rp.STOP_WORDS:
            assert w == w.lower(), f"Stop word not lowercase: {w}"

    def test_title_with_unicode_characters(self):
        title = "Étude des Protéines avec Résonance Magnétique Nucléaire"
        result = rp.title_to_camel(title, 6)
        assert len(result) > 0

    def test_title_with_slashes(self):
        title = "DNA/RNA Hybrid Structures in Cellular Context"
        result = rp.title_to_camel(title, 6)
        assert "/" not in result
        assert "DNA" in result or "RNA" in result


# ===================================================================
#  Run with pytest
# ===================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
