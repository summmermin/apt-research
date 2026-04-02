import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import date
from config import API_KEY

TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
RENT_URL  = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"


def _get(item, tag: str) -> str:
    return (item.findtext(tag) or "").strip()


def _parse_amount(val: str) -> int:
    try:
        return int(val.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _call_api(url: str, lawd_cd: str, deal_ymd: str) -> list:
    params = {
        "serviceKey": API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    code = (root.findtext(".//resultCode") or "").strip()
    if code not in ("00", "000"):
        return []
    return root.findall(".//item")


def fetch_trade(lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    items = _call_api(TRADE_URL, lawd_cd, deal_ymd)
    rows = []
    for item in items:
        try:
            rows.append({
                "아파트":   _get(item, "aptNm"),
                "법정동":   _get(item, "umdNm"),
                "전용면적": round(float(_get(item, "excluUseAr") or 0), 1),
                "매매가":   _parse_amount(_get(item, "dealAmount")),  # 만원
                "층":       _get(item, "floor"),
                "건축년도": _get(item, "buildYear"),
                "년월":     deal_ymd,
            })
        except (ValueError, TypeError):
            continue
    return pd.DataFrame(rows)


def fetch_rent(lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    items = _call_api(RENT_URL, lawd_cd, deal_ymd)
    rows = []
    for item in items:
        # 전세만 필터 (월세 제외)
        monthly_rent = _parse_amount(_get(item, "monthlyRentAmount"))
        if monthly_rent > 0:
            continue
        try:
            rows.append({
                "아파트":   _get(item, "aptNm"),
                "법정동":   _get(item, "umdNm"),
                "전용면적": round(float(_get(item, "excluUseAr") or 0), 1),
                "전세가":   _parse_amount(_get(item, "deposit")),  # 만원
                "년월":     deal_ymd,
            })
        except (ValueError, TypeError):
            continue
    return pd.DataFrame(rows)


def get_recent_months(n: int) -> list[str]:
    result = []
    d = date.today()
    for _ in range(n):
        result.append(d.strftime("%Y%m"))
        if d.month == 1:
            d = d.replace(year=d.year - 1, month=12)
        else:
            d = d.replace(month=d.month - 1)
    return result
