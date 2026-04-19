from worker import build_schedule_spec


def test_schedule_uses_weekly_monday_midnight_utc_cron():
    spec = build_schedule_spec()
    assert spec.cron_expressions == ["0 0 * * 1"]
