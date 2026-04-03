import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import API_KEY

TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
RENT_URL  = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"


class ApiError(Exception):
    """공공 API 호출 관련 에러"""
    pass


class ApiLimitExceeded(ApiError):
    """일일 호출 제한 초과"""
    pass


class ApiKeyInvalid(ApiError):
    """API 키가 유효하지 않음"""
    pass


class ApiServiceUnavailable(ApiError):
    """API 서비스 점검 중"""
    pass


# 공공데이터포털 에러 코드 → 사용자 친화적 메시지
_ERROR_MESSAGES = {
    "01": "어플리케이션 에러가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "02": "데이터베이스 에러가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "03": "데이터가 없습니다.",
    "04": "HTTP 에러가 발생했습니다.",
    "10": "잘못된 요청 파라미터입니다.",
    "11": "필수 요청 파라미터가 누락되었습니다.",
    "12": "해당 Open API 서비스가 없습니다.",
    "20": "서비스 접근이 거부되었습니다. API 키를 확인해주세요.",
    "22": "서비스 요청 제한을 초과했습니다. 잠시 후 다시 시도해주세요.",
    "30": "등록되지 않은 서비스 키입니다. data.go.kr에서 API 키를 확인해주세요.",
    "31": "API 키 사용 기한이 만료되었습니다. data.go.kr에서 갱신해주세요.",
    "32": "등록되지 않은 IP입니다.",
    "33": "서명되지 않은 호출입니다.",
    "99": "알 수 없는 에러가 발생했습니다.",
}


def _get(item, tag: str) -> str:
    return (item.findtext(tag) or "").strip()


def _parse_amount(val: str) -> int:
    try:
        return int(val.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _check_api_error(code: str, message: str = ""):
    """API 응답 코드를 확인하고 적절한 예외를 발생시킴"""
    if code in ("00", "000"):
        return

    if code == "22":
        raise ApiLimitExceeded(_ERROR_MESSAGES.get(code, "호출 제한 초과"))
    if code in ("20", "30", "31"):
        raise ApiKeyInvalid(_ERROR_MESSAGES.get(code, "API 키 오류"))

    error_msg = _ERROR_MESSAGES.get(code, f"API 에러 (코드: {code})")
    if message:
        error_msg += f" — {message}"
    raise ApiError(error_msg)


def _call_api(url: str, lawd_cd: str, deal_ymd: str) -> list:
    params = {
        "serviceKey": API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.ConnectionError:
        raise ApiServiceUnavailable("네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요.")
    except requests.Timeout:
        raise ApiServiceUnavailable("API 서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")

    if resp.status_code == 429:
        raise ApiLimitExceeded("API 호출 횟수 제한을 초과했습니다. 잠시 후 다시 시도해주세요.")
    if resp.status_code >= 500:
        raise ApiServiceUnavailable(f"API 서버 오류입니다 (HTTP {resp.status_code}). 잠시 후 다시 시도해주세요.")
    resp.raise_for_status()

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        raise ApiError("API 응답을 파싱할 수 없습니다. 잠시 후 다시 시도해주세요.")

    code = (root.findtext(".//resultCode") or "").strip()
    message = (root.findtext(".//resultMsg") or "").strip()
    _check_api_error(code, message)

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
                "매매가":   _parse_amount(_get(item, "dealAmount")),
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
        monthly_rent = _parse_amount(_get(item, "monthlyRentAmount"))
        if monthly_rent > 0:
            continue
        try:
            rows.append({
                "아파트":   _get(item, "aptNm"),
                "법정동":   _get(item, "umdNm"),
                "전용면적": round(float(_get(item, "excluUseAr") or 0), 1),
                "전세가":   _parse_amount(_get(item, "deposit")),
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


def fetch_all_parallel(lawd_cd: str, months: int, progress_callback=None):
    """매매 + 전세 데이터를 병렬로 조회. progress_callback(완료수, 전체수, 메시지)"""
    month_list = get_recent_months(months)
    total = len(month_list) * 2
    completed = 0
    errors = []

    trade_frames = []
    rent_frames = []

    def _fetch_trade(ym):
        return ("trade", ym, fetch_trade(lawd_cd, ym))

    def _fetch_rent(ym):
        return ("rent", ym, fetch_rent(lawd_cd, ym))

    tasks = []
    for ym in month_list:
        tasks.append(("trade", ym, _fetch_trade))
        tasks.append(("rent", ym, _fetch_rent))

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        for kind, ym, fn in tasks:
            future = executor.submit(fn, ym)
            futures[future] = (kind, ym)

        for future in as_completed(futures):
            kind, ym = futures[future]
            completed += 1
            ym_display = f"{ym[:4]}년 {int(ym[4:])}월"

            try:
                result_kind, _, df = future.result()
                if result_kind == "trade" and not df.empty:
                    trade_frames.append(df)
                elif result_kind == "rent" and not df.empty:
                    rent_frames.append(df)
            except ApiLimitExceeded as e:
                errors.append(("limit", str(e)))
                break
            except ApiKeyInvalid as e:
                errors.append(("key", str(e)))
                break
            except ApiServiceUnavailable as e:
                errors.append(("unavailable", f"{ym_display}: {e}"))
            except ApiError as e:
                errors.append(("api", f"{ym_display}: {e}"))
            except Exception as e:
                errors.append(("unknown", f"{ym_display}: {e}"))

            if progress_callback:
                label = "매매" if kind == "trade" else "전세"
                progress_callback(completed, total, f"{label} {ym_display} 조회중...")

    trade = pd.concat(trade_frames) if trade_frames else pd.DataFrame()
    rent = pd.concat(rent_frames) if rent_frames else pd.DataFrame()
    return trade, rent, errors
