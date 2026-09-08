import csv

from Hail_Mary.edge.accuracy import AccuracyLog


def test_records_and_reports_sample_count():
    log = AccuracyLog()

    log.record(detected_count=3, actual_count=3)
    log.record(detected_count=2, actual_count=3)

    assert len(log) == 2


def test_mae_is_mean_absolute_error():
    log = AccuracyLog()
    log.record(detected_count=3, actual_count=3)  # error 0
    log.record(detected_count=5, actual_count=3)  # error 2

    assert log.mae() == 1.0


def test_within_tolerance_rate_counts_samples_within_the_given_error():
    log = AccuracyLog()
    log.record(detected_count=3, actual_count=3)  # error 0 -> within tolerance 1
    log.record(detected_count=4, actual_count=3)  # error 1 -> within tolerance 1
    log.record(detected_count=6, actual_count=3)  # error 3 -> NOT within tolerance 1

    assert log.within_tolerance_rate(tolerance=1) == 2 / 3


def test_exact_match_rate_requires_zero_error():
    log = AccuracyLog()
    log.record(detected_count=3, actual_count=3)
    log.record(detected_count=4, actual_count=3)

    assert log.exact_match_rate() == 0.5


def test_meets_kpi_true_when_90_percent_within_one_person_over_20_plus_samples():
    # 제안서.md 8.1절 KPI: 오차 ±1명 이내(또는 정확도 90% 이상), 4.5절: 20~30회 샘플링
    log = AccuracyLog()
    for _ in range(18):
        log.record(detected_count=3, actual_count=3)
    for _ in range(2):
        log.record(detected_count=10, actual_count=3)  # big misses

    assert log.within_tolerance_rate(tolerance=1) == 0.9
    assert log.meets_kpi() is True


def test_meets_kpi_false_when_rate_below_target_even_with_enough_samples():
    log = AccuracyLog()
    for _ in range(10):
        log.record(detected_count=3, actual_count=3)
    for _ in range(10):
        log.record(detected_count=6, actual_count=3)

    assert log.meets_kpi() is False


def test_meets_kpi_false_when_not_enough_samples_yet_even_if_rate_is_perfect():
    # 4.5절 방법론: 20~30회 샘플링 전에는 KPI 충족을 주장할 수 없음
    log = AccuracyLog()
    for _ in range(5):
        log.record(detected_count=3, actual_count=3)

    assert log.within_tolerance_rate(tolerance=1) == 1.0
    assert log.meets_kpi() is False


def test_empty_log_reports_zero_without_dividing_by_zero():
    log = AccuracyLog()

    assert log.mae() == 0.0
    assert log.within_tolerance_rate() == 0.0
    assert log.meets_kpi() is False


def test_summary_reports_all_kpi_metrics():
    log = AccuracyLog()
    log.record(detected_count=3, actual_count=3)

    summary = log.summary()

    assert summary["samples"] == 1
    assert summary["mae"] == 0.0
    assert summary["exact_match_rate"] == 1.0
    assert summary["within_1_rate"] == 1.0
    assert summary["meets_kpi"] is False  # only 1 sample, not enough to claim KPI met


def test_save_csv_writes_a_real_csv_file(tmp_path):
    log = AccuracyLog()
    log.record(detected_count=3, actual_count=2, label="14:00")

    out_path = tmp_path / "accuracy.csv"
    log.save_csv(out_path)

    with open(out_path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows == [{"label": "14:00", "detected_count": "3", "actual_count": "2", "abs_error": "1"}]
