import pytest

import canonical


def test_read_round_trip(tmp_path):
    rows = [{"period": "2025-01", "customer": "Acme", "amount": 100.0}]
    canonical.write("sales", rows, tmp_path / "sales.csv")
    assert canonical.read("sales", tmp_path / "sales.csv") == rows


def test_read_rejects_bad_period(tmp_path):
    (tmp_path / "s.csv").write_text("period,customer,amount\n2025/1,Acme,1\n")
    with pytest.raises(canonical.CanonicalError, match="row 2"):
        canonical.read("sales", tmp_path / "s.csv")


def test_apply_account_map_is_pure_and_complete():
    rows = [{"period": "2025-01", "account": "Hosting", "amount": 5.0, "basis": "accrual", "account_type": ""}]
    out = canonical.apply_account_map(rows, {"Hosting": {"account_type": "cogs"}})
    assert out[0]["account_type"] == "cogs" and rows[0]["account_type"] == ""


def test_apply_account_map_names_unmapped():
    with pytest.raises(canonical.CanonicalError, match="Rent"):
        canonical.apply_account_map([{"account": "Rent", "account_type": ""}], {})


def test_name_key():
    assert canonical.name_key("  ACME   Inc ") == canonical.name_key("Acme Inc")


def test_read_rejects_bad_number_with_row(tmp_path):
    (tmp_path / "s.csv").write_text("period,customer,amount\n2025-01,Acme,1\n2025-02,Acme,$5\n")
    with pytest.raises(canonical.CanonicalError, match="row 3"):
        canonical.read("sales", tmp_path / "s.csv")


def test_read_rejects_missing_column(tmp_path):
    (tmp_path / "s.csv").write_text("period,customer\n2025-01,Acme\n")
    with pytest.raises(canonical.CanonicalError, match="amount"):
        canonical.read("sales", tmp_path / "s.csv")


def test_read_rejects_unknown_kind(tmp_path):
    with pytest.raises(canonical.CanonicalError, match="nope"):
        canonical.read("nope", tmp_path / "x.csv")


def test_dates_and_optional_end_date(tmp_path):
    rows = [{"customer": "A", "plan": "Pro", "interval": "month", "start_date": "2025-01-15",
             "end_date": "", "amount": 50.0, "currency": "USD"}]
    canonical.write("subs", rows, tmp_path / "subs.csv")
    assert canonical.read("subs", tmp_path / "subs.csv") == rows
    (tmp_path / "bad.csv").write_text(
        "customer,plan,interval,start_date,end_date,amount,currency\nA,Pro,month,15/01/2025,,50,USD\n")
    with pytest.raises(canonical.CanonicalError, match="row 2"):
        canonical.read("subs", tmp_path / "bad.csv")


def test_account_type_validated_when_present(tmp_path):
    (tmp_path / "p.csv").write_text("period,account,account_type,amount,basis\n2025-01,Sales,bogus,1,accrual\n")
    with pytest.raises(canonical.CanonicalError, match="row 2"):
        canonical.read("pl", tmp_path / "p.csv")


def test_apply_account_map_sets_subtype_for_bs():
    rows = [{"account": "Checking", "account_type": "", "subtype": ""}]
    out = canonical.apply_account_map(rows, {"Checking": {"account_type": "asset", "subtype": "cash"}})
    assert out[0]["subtype"] == "cash" and rows[0]["subtype"] == ""


def test_apply_account_map_lists_every_unmapped_account():
    rows = [{"account": "Rent"}, {"account": "Fuel"}, {"account": "Rent"}]
    with pytest.raises(canonical.CanonicalError) as exc:
        canonical.apply_account_map(rows, {})
    assert "Rent" in str(exc.value) and "Fuel" in str(exc.value)
