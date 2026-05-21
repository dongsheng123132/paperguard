from paperguard.core.pdf import Document, PageText
from paperguard.detectors import dup_numbers


def test_identical_number_sequence_flagged():
    text = (
        "Group A scores: 4.21, 5.33, 3.18, 4.27, 5.10, 3.92, 4.55, 5.01. "
        "We measured each subject across the morning and afternoon sessions to ensure stability.\n\n"
        "Group B scores: 4.21, 5.33, 3.18, 4.27, 5.10, 3.92, 4.55, 5.01. "
        "Independent recording was used and quality-control reviewed by a second rater."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    assert res.findings, "两组完全相同的数字序列应该被捕获"
    assert res.findings[0].metadata["consecutive"] >= 5


def test_distinct_numbers_no_flag():
    text = (
        "Cohort 1 values: 1.23, 4.56, 7.89, 2.34, 5.67, 8.90. "
        "These were collected at baseline visit and reviewed by the PI for completeness.\n\n"
        "Cohort 2 values: 9.87, 6.54, 3.21, 0.12, 4.32, 7.65. "
        "Collection occurred during the follow-up visit three months later, also reviewed by PI."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    assert not res.findings


def test_repeated_p_thresholds_no_flag():
    text = (
        "Statistical significance was defined as p < 0.05. The same p < 0.05 threshold "
        "was used for all primary and secondary comparisons. Adjusted p < 0.05 values "
        "were interpreted as significant, and unadjusted p < 0.05 values were reported "
        "only in exploratory tables."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    assert not res.findings


def test_table_continuation_requires_stronger_signal():
    text = (
        "TABLE 1 Baseline characteristics. Overall sample n = 143 CG n = 74 IG n = 69 "
        "Age 62.4 ± 8.3 63.1 ± 7.9 61.8 ± 8.8 BMI 27.1 ± 4.2 26.8 ± 4.1 27.5 ± 4.3 "
        "P-value 0.15 0.22 0.40 0.66 0.18 0.20 0.04.\n\n"
        "TABLE 1 Continued. Baseline characteristics. Overall sample n = 143 CG n = 74 IG n = 69 "
        "Medication 5.3 1.5 5.5 5.3 1.5 5.5 P-value 0.15 0.22 0.40 0.66 0.18 0.20 0.04."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    assert not res.findings


def test_doi_and_journal_cruft_ignored():
    """DOI / 期刊页眉里的"数字"不应被当作论文数据."""
    text = (
        "doi: 10.3389/fphys.2024.1441076\n"
        "Frontiers in Physiology | www.frontiersin.org\n"
        "Volume 15 | Article 1441076 | Page 8\n"
        "We measured outcomes A, B, C, D in three independent cohorts; "
        "values were 2.31, 4.67, 1.05, 3.88 respectively.\n\n"
        "doi: 10.3389/fphys.2024.1441076\n"
        "Frontiers in Physiology | www.frontiersin.org\n"
        "Volume 15 | Article 1441076 | Page 9\n"
        "Secondary analysis confirmed the pattern in 5.12, 6.74, 2.20, 4.99 values "
        "from the validation cohort, replicating earlier findings."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    # 即便 doi/article id 重复出现,不应触发 dup_numbers
    assert not res.findings, f"DOI/期刊号被误判为数据: {[f.detail for f in res.findings]}"


def test_p_threshold_alone_not_flagged():
    """段内反复出现 p<0.05 不应只因 4 个 0.05 就报"内部重复"."""
    text = (
        "Group A vs control showed significant differences in measure X (p<0.05) "
        "and measure Y (p<0.05); secondary outcomes also reached significance (p<0.05) "
        "while the exploratory measure trended in the same direction (p<0.05). "
        "Effect sizes were small to moderate across all comparisons in this analysis."
    )
    doc = Document(source="<inline>", pages=[PageText(1, text)])
    res = dup_numbers.run(doc)
    # 只 4 个 0.05 不该触发 (k=5)
    internal = [f for f in res.findings if "连续重复" in f.title]
    assert not internal, f"p<0.05 多次提及被误报: {[f.detail for f in internal]}"
