import streamlit as st
import pandas as pd
from api import fetch_trade, fetch_rent, fetch_all_parallel, ApiLimitExceeded, ApiKeyInvalid
from lawd_codes import LAWD_CODES


def fmt_price(만원: float) -> str:
    """만원 단위를 억/만 한국식 표기로 변환"""
    억 = int(만원 // 10000)
    만 = int(만원 % 10000)
    if 억 and 만:
        return f"{억}억 {만:,}만"
    if 억:
        return f"{억}억"
    return f"{만:,}만"


def render_sidebar():
    """사이드바 렌더링. 필터 조건 dict 반환."""
    with st.sidebar:
        st.header("검색 조건")

        시도 = st.selectbox("시/도", list(LAWD_CODES.keys()))
        구군 = st.selectbox("구/군", list(LAWD_CODES[시도].keys()))
        lawd_cd = LAWD_CODES[시도][구군]

        기간옵션 = {"6개월": 6, "1년": 12, "2년": 24, "3년": 36}
        기간 = st.selectbox("조회 기간", list(기간옵션.keys()), index=1)
        months = 기간옵션[기간]

        평형옵션 = {
            "전체": (0, 9999),
            "소형 (~60㎡)": (0, 60),
            "중소형 (60~85㎡)": (60, 85),
            "중대형 (85㎡~)": (85, 9999),
        }
        평형 = st.selectbox("평형대", list(평형옵션.keys()))
        면적_min, 면적_max = 평형옵션[평형]

        키워드 = st.text_input("아파트명 검색 (선택)", placeholder="예: 래미안, 힐스테이트")

        st.subheader("가격대 (만원)")
        가격_min = st.number_input("최소 매매가", min_value=0, value=0, step=5000, format="%d")
        가격_max = st.number_input("최대 매매가", min_value=0, value=0, step=5000, format="%d",
                                  help="0이면 제한 없음")

        st.divider()
        st.caption("전세가율 = 전세 보증금 / 매매가 × 100\n\n🟢 60% 미만 안전  🟡 60~70% 주의  🔴 70%↑ 위험")

    return {
        "시도": 시도, "구군": 구군, "lawd_cd": lawd_cd,
        "months": months,
        "면적_min": 면적_min, "면적_max": 면적_max,
        "키워드": 키워드,
        "가격_min": 가격_min, "가격_max": 가격_max,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_all(lawd_cd: str, months: int):
    """캐시된 병렬 데이터 로딩 (progress bar 제외 — 캐시 호환성)"""
    trade, rent, errors = fetch_all_parallel(lawd_cd, months)
    return trade, rent, errors


def load_data(filters: dict):
    """데이터 로딩 + 필터 적용 + 에러 표시. (trade_df, rent_df) 반환."""
    lawd_cd = filters["lawd_cd"]
    months = filters["months"]

    # 캐시 미스 시에만 progress bar 표시
    cache_key = f"{lawd_cd}_{months}"
    if cache_key not in st.session_state.get("_loaded_keys", set()):
        bar = st.progress(0, text="데이터 불러오는 중...")

        def on_progress(done, total, msg):
            bar.progress(done / total, text=msg)

        trade_df, rent_df, errors = fetch_all_parallel(lawd_cd, months, progress_callback=on_progress)
        bar.empty()

        # 캐시에도 저장
        _cached_fetch_all(lawd_cd, months)
        if "_loaded_keys" not in st.session_state:
            st.session_state["_loaded_keys"] = set()
        st.session_state["_loaded_keys"].add(cache_key)
    else:
        trade_df, rent_df, errors = _cached_fetch_all(lawd_cd, months)

    # 에러 표시
    _display_errors(errors)

    # 필터 적용
    trade_df, rent_df = _apply_filters(trade_df, rent_df, filters)

    return trade_df, rent_df


def _display_errors(errors: list):
    """API 에러를 종류별로 사용자 친화적으로 표시"""
    if not errors:
        return

    error_types = set(e[0] for e in errors)

    if "limit" in error_types:
        st.error(
            "**API 일일 호출 제한 초과**\n\n"
            "공공데이터포털의 일일 호출 횟수를 초과했습니다. "
            "일부 월의 데이터만 표시될 수 있습니다.\n\n"
            "**해결 방법:** 내일 다시 시도하거나, data.go.kr에서 호출 제한 상향을 신청하세요."
        )
        return

    if "key" in error_types:
        st.error(
            "**API 키 오류**\n\n"
            "API 키가 유효하지 않거나 만료되었습니다.\n\n"
            "**해결 방법:** `.streamlit/secrets.toml` 파일의 `API_KEY` 값을 확인하고, "
            "data.go.kr에서 키 상태를 점검하세요."
        )
        return

    if "unavailable" in error_types:
        fail_count = sum(1 for e in errors if e[0] == "unavailable")
        st.warning(
            f"**일부 데이터 조회 실패** ({fail_count}건)\n\n"
            "API 서버 응답 지연 또는 네트워크 문제로 일부 월의 데이터를 가져오지 못했습니다. "
            "표시된 데이터는 정상 조회된 월 기준입니다."
        )
    elif "api" in error_types or "unknown" in error_types:
        fail_count = len(errors)
        st.warning(f"**일부 데이터 조회 실패** ({fail_count}건) — 정상 조회된 데이터만 표시됩니다.")


def _apply_filters(trade_df: pd.DataFrame, rent_df: pd.DataFrame, filters: dict):
    """필터 조건 적용"""
    면적_min = filters["면적_min"]
    면적_max = filters["면적_max"]
    가격_min = filters["가격_min"]
    가격_max = filters["가격_max"]
    키워드 = filters["키워드"]

    if not trade_df.empty:
        trade_df = trade_df[
            (trade_df["전용면적"] >= 면적_min) & (trade_df["전용면적"] < 면적_max)
        ]
    if not rent_df.empty:
        rent_df = rent_df[
            (rent_df["전용면적"] >= 면적_min) & (rent_df["전용면적"] < 면적_max)
        ]

    if not trade_df.empty and 가격_min > 0:
        trade_df = trade_df[trade_df["매매가"] >= 가격_min]
    if not trade_df.empty and 가격_max > 0:
        trade_df = trade_df[trade_df["매매가"] <= 가격_max]

    if 키워드:
        if not trade_df.empty:
            trade_df = trade_df[trade_df["아파트"].str.contains(키워드, na=False)]
        if not rent_df.empty:
            rent_df = rent_df[rent_df["아파트"].str.contains(키워드, na=False)]

    if not trade_df.empty:
        trade_df["평당가"] = (trade_df["매매가"] / trade_df["전용면적"] * 3.3058).round(0)

    return trade_df, rent_df
