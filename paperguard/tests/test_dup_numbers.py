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
