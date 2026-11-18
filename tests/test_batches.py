"""Listing a filing year's IRS batches, for indexes with and without a batch column (no network)."""
import pytest

from grantmatch import foundations as F

NEW = ("RETURN_ID,FILING_TYPE,EIN,TAX_PERIOD,SUB_DATE,TAXPAYER_NAME,RETURN_TYPE,DLN,OBJECT_ID,XML_BATCH_ID\n"
       "1,EFILE,100000001,202312,2024,SAMPLE FOUNDATION A,990PF,1,111,2024_TEOS_XML_04a\n"
       "2,EFILE,100000002,202312,2024,SAMPLE FOUNDATION B,990PF,2,222,2024_TEOS_XML_04A\n"
       "3,EFILE,100000003,202312,2024,SAMPLE CHARITY,990,3,333,2024_TEOS_XML_05A\n")
OLD = ("RETURN_ID,FILING_TYPE,EIN,TAX_PERIOD,SUB_DATE,TAXPAYER_NAME,RETURN_TYPE,DLN,OBJECT_ID\n"
       "1,EFILE,100000001,202112,2022,SAMPLE FOUNDATION A,990PF,1,444\n"
       "2,EFILE,100000003,202112,2022,SAMPLE CHARITY,990,2,555\n")


class Resp:
    def __init__(self, status, text=""):
        self.status_code, self.content = status, text.encode("latin-1")


class FakeSession:
    def __init__(self, index, zips):
        self.index, self.zips, self.heads = index, set(zips), []

    def get(self, url, timeout=None):
        return Resp(200, self.index) if self.index is not None else Resp(404)

    def head(self, url, allow_redirects=True, timeout=None):
        name = url.rsplit("/", 1)[-1][:-4]
        self.heads.append(name)
        return Resp(200) if name in self.zips else Resp(302)


def test_batch_ids_uppercase_the_zip_name(monkeypatch):
    monkeypatch.setattr(F, "session", FakeSession(NEW, []))
    assert F.batch_ids(2024) == {"2024_TEOS_XML_04A": {"111", "222"}}


def test_a_second_zip_the_index_never_names_is_read(monkeypatch):
    # the index files 05B's returns under 05A
    fake = FakeSession(NEW, ["2024_TEOS_XML_04A", "2024_TEOS_XML_04B"])
    monkeypatch.setattr(F, "session", fake)
    assert F.batch_ids(2024) == {"2024_TEOS_XML_04A": {"111", "222"}, "2024_TEOS_XML_04B": {"111", "222"}}


def test_old_index_reads_every_zip_of_the_year(monkeypatch):
    fake = FakeSession(OLD, ["2022_TEOS_XML_01A", "2022_TEOS_XML_11A", "2022_TEOS_XML_11B"])
    monkeypatch.setattr(F, "session", fake)
    assert F.batch_ids(2022) == {z: {"444"} for z in fake.zips}
    assert "2022_TEOS_XML_11C" in fake.heads and "2022_TEOS_XML_01B" in fake.heads


def test_old_index_without_zips_fails_loudly(monkeypatch):
    monkeypatch.setattr(F, "session", FakeSession(OLD, []))
    with pytest.raises(RuntimeError, match="no batch zips"):
        F.batch_ids(2022)


def test_no_index_yet(monkeypatch):
    monkeypatch.setattr(F, "session", FakeSession(None, []))
    assert F.batch_ids(2027) is None


def test_only_recent_filers_are_listed():
    latest = {"1": {"ein": "1"}, "2": {"ein": "2"}, "3": {"ein": "3"}}
    filed = {"1": 2026, "2": 2025, "3": 2024}
    assert set(F.current(latest, filed, 2026)) == {"1", "2"}
