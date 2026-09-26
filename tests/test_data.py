import io
import zipfile
from datetime import date

import pandas as pd

from miratrade.data.options import normalise_flow, parse_cboe_chain, parse_occ
from miratrade.data.sec import parse_bulk_zip, parse_daily_index, parse_form4_xml

FORM4 = """<ownershipDocument>
  <issuer><issuerCik>1</issuerCik><issuerName>Acme Corp</issuerName>
    <issuerTradingSymbol>acme</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>99</rptOwnerCik><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-03</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50.5</value></transactionPricePerShare></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>5000</value>
        </sharesOwnedFollowingTransaction></postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parse_form4_xml():
    df = parse_form4_xml(FORM4, accession="a1", filing_date="20260805")
    r = df.iloc[0]
    assert r.ticker == "ACME" and r.code == "P" and r.is_officer and not r.is_director
    assert r.issuer_cik == "1"
    assert r.value == 50_500 and r.delta_own_pct == 0.25
    assert r.filing_date == pd.Timestamp("2026-08-05") and r.trade_date == pd.Timestamp("2026-08-03")


def test_parse_daily_index_dedupes_and_filters():
    idx = ("Form Type   Company Name   CIK   Date Filed  File Name\n" + "-" * 40 + "\n"
           "4           ACME CORP      1     20260805    edgar/data/1/0001-26-1.txt\n"
           "4           DOE JANE       99    20260805    edgar/data/1/0001-26-1.txt\n"
           "4/A         ACME CORP      1     20260805    edgar/data/1/0001-26-2.txt\n"
           "10-K        ACME CORP      1     20260805    edgar/data/1/0001-26-3.txt\n")
    assert parse_daily_index(idx) == [("edgar/data/1/0001-26-1.txt", "20260805")]


def test_parse_bulk_zip():
    tables = {
        "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tISSUERNAME\tISSUERTRADINGSYMBOL\tISSUERCIK\n"
                          "a1\t05-AUG-2026\tAcme\tACME\t0000000042\n",
        "REPORTINGOWNER.tsv": "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
                              "a1\t99\tDoe\tDirector,Officer\tCFO\n",
        "NONDERIV_TRANS.tsv": "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tSHRS_OWND_FOLWNG_TRANS\n"
                              "a1\t01-AUG-2026\tP\t100\t10\t100\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in tables.items():
            zf.writestr(name, body)
    r = parse_bulk_zip(buf.getvalue()).iloc[0]
    assert r.ticker == "ACME" and r.is_officer and r.is_director and r.value == 1000
    assert r.issuer_cik == "42"
    assert r.delta_own_pct == 1.0  # brand-new position


def test_parse_occ():
    assert parse_occ("AAPL260918C00200000") == ("AAPL", date(2026, 9, 18), "C", 200.0)
    assert parse_occ("garbage") is None


def test_normalise_flow_aliases():
    raw = pd.DataFrame({"Symbol": ["nvda"], "Executed At": ["2026-09-01 10:31"], "Expiration": ["2026-09-19"],
                        "Put/Call": ["call"], "Strike": [120], "Size": [3000], "OI": [400],
                        "Premium": ["$1,250,000"], "Stock Price": [118], "Side": ["Ask"]})
    raw = raw.rename(columns={"Put/Call": "put_call"})
    r = normalise_flow(raw).iloc[0]
    assert r.ticker == "NVDA" and r.type == "C" and r.premium == 1_250_000 and r.side == "ask"
    assert r.date == pd.Timestamp("2026-09-01")


def test_parse_cboe_chain():
    payload = {"data": {"symbol": "XYZ", "current_price": 100, "options": [
        {"option": "XYZ261016C00105000", "volume": 2000, "open_interest": 100, "last_trade_price": 2.5},
        {"option": "XYZ261016P00095000", "volume": 0, "open_interest": 100, "last_trade_price": 1.0}]}}
    df = parse_cboe_chain(payload, date(2026, 9, 24))
    assert len(df) == 1 and df.iloc[0].premium == 500_000 and df.iloc[0].strike == 105


class _Resp:
    def __init__(self, status, content=b"ok"):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _client(tmp_path, statuses):
    from miratrade.data.sec import SecClient

    c = SecClient(user_agent="test test@example.com", cache_dir=tmp_path, retries=3, backoff=0)
    replies = iter(_Resp(s) for s in statuses)
    c.session.get = lambda url, timeout: next(replies)
    return c


def test_sec_client_retries_transient_errors(tmp_path):
    c = _client(tmp_path, [503, 429, 200])
    assert c.get("https://www.sec.gov/x.txt") == b"ok"
    assert (tmp_path / "www.sec.gov_x.txt").exists()


def test_sec_client_gives_up_after_retries(tmp_path):
    import pytest

    c = _client(tmp_path, [503] * 4)
    with pytest.raises(RuntimeError):
        c.get("https://www.sec.gov/y.txt")
    assert _client(tmp_path, [404]).get("https://www.sec.gov/z.txt") is None


def test_sec_client_missing_statuses(tmp_path):
    import pytest

    # EDGAR answers a holiday's missing daily index with 403, not 404.
    assert _client(tmp_path, [403]).get("https://www.sec.gov/idx", missing=(403, 404)) is None
    with pytest.raises(RuntimeError):
        _client(tmp_path, [403]).get("https://www.sec.gov/other")


def test_clean_insiders_drops_filing_errors():
    from miratrade.data.sec import clean_insiders

    rows = pd.DataFrame({
        "ticker": ["ACME", "NONE", "PBLSX", "REEMF", "BRK.A", "SPGX"],
        "price": [50.0, 10.0, 12.0, 24_035_774.4, 700_000.0, 30.0],
        "shares": [1_000, 1_000, 1_000, 100_149_100, 10, 1_000],
    }).assign(value=lambda d: d["price"] * d["shares"])
    kept, stats = clean_insiders(rows)
    # REEMF typed the total into the price field; BRK.A is a genuinely high price on few shares;
    # SPGX is a four-letter stock, not a five-letter fund ticker.
    assert list(kept["ticker"]) == ["ACME", "BRK.A", "SPGX"]
    assert stats == {"placeholder_ticker": 1, "fund_ticker": 1, "total_as_price": 1}
