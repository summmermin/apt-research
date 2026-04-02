import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from api import fetch_trade, fetch_rent, get_recent_months
from lawd_codes import LAWD_CODES

st.set_page_config(page_title="아파트 시세 탐색기", layout="wide")
st.title("아파트 시세 탐색기")
st.caption("국토교통부 실거래가 기반 · 매매가 추이 & 전세가율 분석")


# ── 유틸 함수 ─────────────────────────────────────────────────────────
def fmt_price(만원: float) -> str:
    """만원 단위를 억/만 한국식 표기로 변환"""
    억 = int(만원 // 10000)
    만 = int(만원 % 10000)
    if 억 and 만:
        return f"{억}억 {만:,}만"
    if 억:
        return f"{억}억"
    return f"{만:,}만"


# ── Sidebar ───────────────────────────────────────────────────────────
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


# ── Data Loading ──────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_trade(lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    return fetch_trade(lawd_cd, deal_ymd)

@st.cache_data(ttl=3600, show_spinner=False)
def load_rent(lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    return fetch_rent(lawd_cd, deal_ymd)


def load_all(lawd_cd: str, months: int):
    month_list = get_recent_months(months)
    total = len(month_list) * 2
    bar = st.progress(0, text="데이터 불러오는 중...")

    trade_frames = []
    for i, ym in enumerate(month_list):
        bar.progress((i + 1) / total, text=f"매매 {ym[:4]}년 {int(ym[4:])}월 조회중...")
        try:
            t = load_trade(lawd_cd, ym)
            if not t.empty:
                trade_frames.append(t)
        except Exception:
            pass

    rent_frames = []
    for i, ym in enumerate(month_list):
        bar.progress((len(month_list) + i + 1) / total, text=f"전세 {ym[:4]}년 {int(ym[4:])}월 조회중...")
        try:
            r = load_rent(lawd_cd, ym)
            if not r.empty:
                rent_frames.append(r)
        except Exception:
            pass

    bar.empty()
    trade = pd.concat(trade_frames) if trade_frames else pd.DataFrame()
    rent  = pd.concat(rent_frames)  if rent_frames  else pd.DataFrame()
    return trade, rent


trade_df, rent_df = load_all(lawd_cd, months)

# 평형 필터
if not trade_df.empty:
    trade_df = trade_df[
        (trade_df["전용면적"] >= 면적_min) & (trade_df["전용면적"] < 면적_max)
    ]
if not rent_df.empty:
    rent_df = rent_df[
        (rent_df["전용면적"] >= 면적_min) & (rent_df["전용면적"] < 면적_max)
    ]

# 가격 필터
if not trade_df.empty and 가격_min > 0:
    trade_df = trade_df[trade_df["매매가"] >= 가격_min]
if not trade_df.empty and 가격_max > 0:
    trade_df = trade_df[trade_df["매매가"] <= 가격_max]

# 키워드 필터
if 키워드:
    if not trade_df.empty:
        trade_df = trade_df[trade_df["아파트"].str.contains(키워드, na=False)]
    if not rent_df.empty:
        rent_df = rent_df[rent_df["아파트"].str.contains(키워드, na=False)]

# 평당가 계산 (전용면적 기준)
if not trade_df.empty:
    trade_df["평당가"] = (trade_df["매매가"] / trade_df["전용면적"] * 3.3058).round(0)

if trade_df.empty:
    st.warning("해당 조건의 매매 거래 데이터가 없습니다.")
    st.stop()


# ── 아파트 선택 ────────────────────────────────────────────────────────
apt_list = sorted(trade_df["아파트"].unique().tolist())
selected_apts = st.multiselect(
    f"아파트 선택 — {시도} {구군} ({len(apt_list)}개 단지 검색됨, 비워두면 지역 전체)",
    apt_list,
    placeholder="아파트를 선택하면 해당 단지만 분석합니다...",
)

if selected_apts:
    trade_df = trade_df[trade_df["아파트"].isin(selected_apts)]
    if not rent_df.empty:
        rent_df = rent_df[rent_df["아파트"].isin(selected_apts)]


# ── Tabs ──────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "매매가 분석", "평당가 비교", "거래량 분석", "전세가율 분석", "수익률 시뮬레이터", "종합 추천",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 1: 매매가 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    monthly = (
        trade_df.groupby("년월")["매매가"]
        .agg(평균="mean", 최저="min", 최고="max", 거래건수="count")
        .reset_index()
        .sort_values("년월")
    )
    monthly["년월표시"] = monthly["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["최고"],
        mode="lines", name="최고가",
        line=dict(dash="dot", color="lightcoral"), opacity=0.6,
    ))
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["평균"],
        mode="lines+markers", name="평균가",
        line=dict(color="steelblue", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["최저"],
        mode="lines", name="최저가",
        line=dict(dash="dot", color="lightblue"), opacity=0.6,
    ))
    fig.update_layout(
        title=f"{시도} {구군} 월별 매매가 추이 (만원)",
        yaxis_tickformat=",",
        hovermode="x unified",
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 요약 메트릭
    latest = monthly.iloc[-1]
    prev   = monthly.iloc[-2] if len(monthly) >= 2 else latest
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "최근월 평균 매매가",
        f"{latest['평균']:,.0f}만원",
        delta=f"{latest['평균'] - prev['평균']:+,.0f}만원",
    )
    col2.metric("최근월 최고가",    f"{latest['최고']:,.0f}만원")
    col3.metric("최근월 최저가",    f"{latest['최저']:,.0f}만원")
    col4.metric("최근월 거래건수",  f"{int(latest['거래건수'])}건")

    st.divider()

    # ── 전고점 대비 현재가 ──────────────────────────────────────────────
    st.subheader("전고점 대비 현재가")
    apt_peak = (
        trade_df.groupby("아파트")
        .agg(최고가=("매매가", "max"), 최근거래가=("매매가", "last"))
        .reset_index()
    )
    # 최근 거래가: 가장 최근 년월의 평균
    latest_month = trade_df["년월"].max()
    latest_trades = trade_df[trade_df["년월"] == latest_month]
    apt_latest = latest_trades.groupby("아파트")["매매가"].mean().reset_index(name="최근평균가")
    apt_all_max = trade_df.groupby("아파트")["매매가"].max().reset_index(name="전고점")
    peak_df = apt_all_max.merge(apt_latest, on="아파트")
    peak_df["전고점대비"] = ((peak_df["최근평균가"] / peak_df["전고점"] - 1) * 100).round(1)
    peak_df = peak_df.sort_values("전고점대비")

    if not peak_df.empty:
        # 저평가 / 신고가 하이라이트
        저평가 = peak_df[peak_df["전고점대비"] < -10]
        신고가 = peak_df[peak_df["전고점대비"] >= 0]

        pcol1, pcol2 = st.columns(2)
        with pcol1:
            st.markdown(f"**저평가 구간 (전고점 -10% 이하)** — {len(저평가)}개 단지")
            if not 저평가.empty:
                st.dataframe(
                    저평가.assign(
                        전고점=저평가["전고점"].apply(fmt_price),
                        최근평균가=저평가["최근평균가"].apply(fmt_price),
                        전고점대비=저평가["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
                    )[["아파트", "전고점", "최근평균가", "전고점대비"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("해당 단지 없음")
        with pcol2:
            st.markdown(f"**신고가 경신 (전고점 이상)** — {len(신고가)}개 단지")
            if not 신고가.empty:
                st.dataframe(
                    신고가.sort_values("전고점대비", ascending=False).assign(
                        전고점=신고가["전고점"].apply(fmt_price),
                        최근평균가=신고가["최근평균가"].apply(fmt_price),
                        전고점대비=신고가["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
                    )[["아파트", "전고점", "최근평균가", "전고점대비"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("해당 단지 없음")

    st.divider()

    # 거래 건수 Top 5
    st.subheader("거래 건수 Top 5 아파트")
    top5 = (
        trade_df.groupby("아파트")
        .agg(거래건수=("매매가", "count"), 평균매매가=("매매가", "mean"),
             최저가=("매매가", "min"), 최고가=("매매가", "max"))
        .reset_index()
        .sort_values("거래건수", ascending=False)
        .head(5)
    )
    top5_cols = st.columns(min(len(top5), 5))
    for i, (_, row) in enumerate(top5.iterrows()):
        with top5_cols[i]:
            st.metric(row["아파트"], f"{int(row['거래건수'])}건")
            st.caption(f"평균 {fmt_price(row['평균매매가'])}")

    st.divider()

    # 최근 거래 내역
    st.subheader("최근 거래 내역")
    display = (
        trade_df[["아파트", "법정동", "전용면적", "층", "매매가", "건축년도", "년월"]]
        .copy()
        .sort_values(["년월", "매매가"], ascending=[False, False])
    )
    display.insert(5, "매매가(억)", (display["매매가"] / 10000).round(2))
    st.dataframe(display, use_container_width=True, hide_index=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 2: 평당가 비교
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.subheader(f"{시도} {구군} 평당가 랭킹")
    st.caption("평당가 = 매매가 ÷ 전용면적(㎡) × 3.3058 (1평 환산)")

    # 아파트별 평균 평당가
    pyeong_rank = (
        trade_df.groupby("아파트")
        .agg(평균평당가=("평당가", "mean"), 거래건수=("평당가", "count"),
             평균면적=("전용면적", "mean"))
        .reset_index()
        .sort_values("평균평당가", ascending=False)
    )
    pyeong_rank["평균평당가"] = pyeong_rank["평균평당가"].round(0)
    pyeong_rank["평균면적"] = pyeong_rank["평균면적"].round(1)

    # Top 10 / Bottom 10
    st.markdown("**가장 비싼 아파트 Top 10** (평당가 기준)")
    top10 = pyeong_rank.head(10)
    fig_p = px.bar(
        top10.sort_values("평균평당가"),
        x="평균평당가", y="아파트",
        orientation="h",
        text="평균평당가",
        color="평균평당가",
        color_continuous_scale="Reds",
    )
    fig_p.update_traces(texttemplate="%{text:,.0f}만원", textposition="outside")
    fig_p.update_layout(
        height=400, showlegend=False, coloraxis_showscale=False,
        xaxis_title="평당가 (만원)", yaxis_title="",
    )
    st.plotly_chart(fig_p, use_container_width=True)

    if len(pyeong_rank) > 10:
        st.markdown("**가장 저렴한 아파트 Top 10** (평당가 기준)")
        bottom10 = pyeong_rank.tail(10)
        fig_b = px.bar(
            bottom10.sort_values("평균평당가"),
            x="평균평당가", y="아파트",
            orientation="h",
            text="평균평당가",
            color="평균평당가",
            color_continuous_scale="Blues",
        )
        fig_b.update_traces(texttemplate="%{text:,.0f}만원", textposition="outside")
        fig_b.update_layout(
            height=400, showlegend=False, coloraxis_showscale=False,
            xaxis_title="평당가 (만원)", yaxis_title="",
        )
        st.plotly_chart(fig_b, use_container_width=True)

    st.divider()

    # 전체 평당가 테이블
    st.subheader("전체 평당가 테이블")
    st.dataframe(
        pyeong_rank.assign(
            평균평당가=pyeong_rank["평균평당가"].apply(lambda x: f"{x:,.0f}만원"),
        )[["아파트", "평균면적", "평균평당가", "거래건수"]],
        use_container_width=True, hide_index=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 3: 거래량 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.subheader(f"{시도} {구군} 월별 거래량 추이")
    st.caption("거래량은 가격보다 먼저 움직이는 선행지표입니다. 급증 → 상승 신호 / 급감 → 관망세")

    vol = (
        trade_df.groupby("년월")["매매가"]
        .agg(거래건수="count", 평균가="mean")
        .reset_index()
        .sort_values("년월")
    )
    vol["년월표시"] = vol["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")
    vol["전월대비"] = vol["거래건수"].pct_change().fillna(0) * 100

    # 듀얼 축 차트: 거래량 (바) + 평균가 (라인)
    fig_vol = go.Figure()
    fig_vol.add_trace(go.Bar(
        x=vol["년월표시"], y=vol["거래건수"],
        name="거래건수",
        marker_color=vol["전월대비"].apply(
            lambda x: "salmon" if x < 0 else "steelblue"
        ).tolist(),
        yaxis="y",
    ))
    fig_vol.add_trace(go.Scatter(
        x=vol["년월표시"], y=vol["평균가"],
        name="평균 매매가",
        line=dict(color="orange", width=2),
        yaxis="y2",
    ))
    fig_vol.update_layout(
        title="거래량 vs 평균 매매가",
        yaxis=dict(title="거래건수", side="left"),
        yaxis2=dict(title="평균 매매가 (만원)", overlaying="y", side="right", tickformat=","),
        hovermode="x unified",
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    # 거래량 메트릭
    if len(vol) >= 2:
        최근 = vol.iloc[-1]
        이전 = vol.iloc[-2]
        변화 = 최근["거래건수"] - 이전["거래건수"]
        변화율 = (변화 / 이전["거래건수"] * 100) if 이전["거래건수"] > 0 else 0

        vcol1, vcol2, vcol3, vcol4 = st.columns(4)
        vcol1.metric("최근월 거래건수", f"{int(최근['거래건수'])}건",
                     delta=f"{변화:+.0f}건 ({변화율:+.1f}%)")
        vcol2.metric("전체 평균 거래건수", f"{vol['거래건수'].mean():.0f}건/월")
        vcol3.metric("최다 거래월", f"{vol.loc[vol['거래건수'].idxmax(), '년월표시']}")
        vcol4.metric("최소 거래월", f"{vol.loc[vol['거래건수'].idxmin(), '년월표시']}")

    st.divider()

    # 거래량 전월대비 변화율
    st.subheader("월별 거래량 전월 대비 변화율")
    fig_chg = px.bar(
        vol[1:], x="년월표시", y="전월대비",
        color="전월대비",
        color_continuous_scale=["red", "white", "blue"],
        range_color=[-100, 100],
        labels={"전월대비": "변화율 (%)"},
    )
    fig_chg.add_hline(y=0, line_color="gray")
    fig_chg.update_layout(height=300, coloraxis_showscale=False)
    st.plotly_chart(fig_chg, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 4: 전세가율 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    if rent_df.empty:
        st.info(
            "전세 거래 데이터가 없거나 API 미신청 상태입니다.\n\n"
            "data.go.kr 에서 **'국토교통부 아파트 전월세 자료'** API를 추가 신청해주세요."
        )
        st.stop()

    # 아파트별 평균 전세가율
    avg_trade = trade_df.groupby("아파트")["매매가"].mean().reset_index(name="평균매매가")
    avg_rent  = rent_df.groupby("아파트")["전세가"].mean().reset_index(name="평균전세가")
    ratio_df  = avg_trade.merge(avg_rent, on="아파트").dropna()
    ratio_df["전세가율"] = (ratio_df["평균전세가"] / ratio_df["평균매매가"] * 100).round(1)
    ratio_df = ratio_df.sort_values("전세가율", ascending=False)

    def risk_label(r):
        if r >= 70: return "🔴 위험"
        if r >= 60: return "🟡 주의"
        return "🟢 안전"
    ratio_df["위험도"] = ratio_df["전세가율"].apply(risk_label)

    # 전세가율 기준 안내
    with st.expander("전세가율이란? (기준 설명)", expanded=False):
        st.markdown("""
**전세가율** = 전세 보증금 / 매매가 × 100

아파트의 매매가 대비 전세가 비율로, **갭투자 리스크**를 판단하는 핵심 지표입니다.

| 구간 | 의미 | 해석 |
|------|------|------|
| **60% 미만** | 안전 | 매매가 대비 전세가가 낮아 가격 하락 시에도 보증금 회수 가능성 높음 |
| **60~70%** | 주의 | 갭이 좁아지는 구간. 시장 하락 시 역전세 가능성 있음 |
| **70% 이상** | 위험 | 매매가와 전세가 차이가 작아 소액 갭투자 많은 구간. 하락장에서 깡통전세 위험 |

**활용 팁**
- 전세가율이 **높을수록** 갭투자 비중이 높아 가격 하락 시 급매 가능성 증가
- 전세가율이 **낮을수록** 실수요 비중이 높아 가격 방어력이 상대적으로 강함
- 같은 지역 내에서 단지별 전세가율을 비교하면 투자 과열 단지를 식별할 수 있음
""")

    # 요약 메트릭
    col1, col2, col3 = st.columns(3)
    col1.metric("평균 전세가율",      f"{ratio_df['전세가율'].mean():.1f}%")
    col2.metric("위험 단지 (70%↑)",  f"{(ratio_df['전세가율'] >= 70).sum()}개")
    col3.metric("안전 단지 (60%↓)",  f"{(ratio_df['전세가율'] < 60).sum()}개")

    # 바 차트
    fig2 = px.bar(
        ratio_df, x="아파트", y="전세가율",
        color="전세가율",
        color_continuous_scale=["green", "yellow", "red"],
        range_color=[40, 90],
        title="아파트별 전세가율 (%)",
        labels={"전세가율": "전세가율 (%)"},
    )
    fig2.add_hline(y=70, line_dash="dash", line_color="red",    annotation_text="위험선 70%")
    fig2.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="주의선 60%")
    fig2.update_layout(height=420, xaxis_tickangle=-45, coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

    # 상세 테이블
    st.dataframe(
        ratio_df.assign(
            평균매매가=ratio_df["평균매매가"].apply(lambda x: f"{x:,.0f}만원"),
            평균전세가=ratio_df["평균전세가"].apply(lambda x: f"{x:,.0f}만원"),
            전세가율=ratio_df["전세가율"].apply(lambda x: f"{x:.1f}%"),
        )[["아파트", "평균매매가", "평균전세가", "전세가율", "위험도"]],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # 월별 전세가율 추이
    m_trade = trade_df.groupby("년월")["매매가"].mean().reset_index(name="평균매매가")
    m_rent  = rent_df.groupby("년월")["전세가"].mean().reset_index(name="평균전세가")
    m_ratio = m_trade.merge(m_rent, on="년월")
    m_ratio["전세가율"] = (m_ratio["평균전세가"] / m_ratio["평균매매가"] * 100).round(1)
    m_ratio["년월표시"] = m_ratio["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")
    m_ratio = m_ratio.sort_values("년월")

    fig3 = go.Figure()
    fig3.add_hline(y=70, line_dash="dash", line_color="red",    annotation_text="위험선 70%")
    fig3.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="주의선 60%")
    fig3.add_trace(go.Scatter(
        x=m_ratio["년월표시"], y=m_ratio["전세가율"],
        mode="lines+markers", name="전세가율",
        line=dict(color="steelblue", width=2),
    ))
    fig3.update_layout(
        title="월별 전세가율 추이 (%)",
        yaxis_title="전세가율 (%)",
        height=380,
    )
    st.plotly_chart(fig3, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 5: 수익률 시뮬레이터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.subheader("수익률 시뮬레이터")
    st.caption("조회 기간 내 첫 거래가 → 최근 거래가 비교로 추정 수익률을 계산합니다.")

    # 아파트별 첫 거래 vs 최근 거래 평균
    first_month = trade_df["년월"].min()
    last_month  = trade_df["년월"].max()

    first_trades = trade_df[trade_df["년월"] == first_month].groupby("아파트")["매매가"].mean().reset_index(name="시작평균가")
    last_trades  = trade_df[trade_df["년월"] == last_month].groupby("아파트")["매매가"].mean().reset_index(name="최근평균가")
    profit_df = first_trades.merge(last_trades, on="아파트")
    profit_df["차이"] = profit_df["최근평균가"] - profit_df["시작평균가"]
    profit_df["수익률"] = ((profit_df["최근평균가"] / profit_df["시작평균가"] - 1) * 100).round(1)
    profit_df = profit_df.sort_values("수익률", ascending=False)

    if profit_df.empty:
        st.info("수익률 계산에 충분한 데이터가 없습니다.")
    else:
        st.markdown(f"**기간: {first_month[:4]}.{first_month[4:]} → {last_month[:4]}.{last_month[4:]}**")

        # 요약 메트릭
        scol1, scol2, scol3 = st.columns(3)
        scol1.metric("평균 수익률", f"{profit_df['수익률'].mean():+.1f}%")
        scol2.metric("최고 수익 아파트",
                     profit_df.iloc[0]["아파트"],
                     delta=f"{profit_df.iloc[0]['수익률']:+.1f}%")
        if len(profit_df) >= 2:
            worst = profit_df.iloc[-1]
            scol3.metric("최저 수익 아파트", worst["아파트"],
                         delta=f"{worst['수익률']:+.1f}%")

        st.divider()

        # 수익률 바 차트
        fig_profit = px.bar(
            profit_df, x="아파트", y="수익률",
            color="수익률",
            color_continuous_scale=["red", "white", "blue"],
            range_color=[-30, 30],
            title="아파트별 추정 수익률 (%)",
        )
        fig_profit.add_hline(y=0, line_color="gray")
        fig_profit.update_layout(height=420, xaxis_tickangle=-45, coloraxis_showscale=False)
        st.plotly_chart(fig_profit, use_container_width=True)

        # 상세 테이블
        st.dataframe(
            profit_df.assign(
                시작평균가=profit_df["시작평균가"].apply(fmt_price),
                최근평균가=profit_df["최근평균가"].apply(fmt_price),
                차이=profit_df["차이"].apply(lambda x: f"{'+' if x > 0 else ''}{fmt_price(x)}"),
                수익률=profit_df["수익률"].apply(lambda x: f"{x:+.1f}%"),
            )[["아파트", "시작평균가", "최근평균가", "차이", "수익률"]],
            use_container_width=True, hide_index=True,
        )

        # 투자 시뮬레이션
        st.divider()
        st.subheader("투자 시뮬레이션")
        투자금 = st.number_input("투자금액 (만원)", min_value=1000, value=50000, step=5000, format="%d")
        sim_apt = st.selectbox("아파트 선택", profit_df["아파트"].tolist())

        if sim_apt:
            row = profit_df[profit_df["아파트"] == sim_apt].iloc[0]
            예상수익 = 투자금 * row["수익률"] / 100
            st.markdown(f"""
| 항목 | 값 |
|------|-----|
| 투자금 | **{fmt_price(투자금)}** |
| 기간 | {first_month[:4]}.{first_month[4:]} → {last_month[:4]}.{last_month[4:]} |
| 수익률 | **{row['수익률']:+.1f}%** |
| 예상 수익 | **{fmt_price(abs(예상수익))}** {'이익' if 예상수익 >= 0 else '손실'} |
| 예상 총액 | **{fmt_price(투자금 + 예상수익)}** |
""")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tab 6: 종합 추천
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    st.subheader("종합 추천")
    st.caption("실거래 데이터 기반 객관적 지표 스코어링입니다. 투자 판단은 본인의 책임입니다.")

    # 예산 범위 입력
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        예산_min = st.number_input("최소 예산 (만원)", min_value=0, value=50000, step=5000,
                                  format="%d", key="rec_min")
    with rcol2:
        예산_max = st.number_input("최대 예산 (만원)", min_value=0, value=70000, step=5000,
                                  format="%d", key="rec_max")

    st.markdown(f"**예산 범위: {fmt_price(예산_min)} ~ {fmt_price(예산_max)}**")

    # 예산 범위 내 아파트 필터
    budget_df = trade_df.copy()
    apt_avg = budget_df.groupby("아파트")["매매가"].mean().reset_index(name="평균매매가")
    budget_apts = apt_avg[(apt_avg["평균매매가"] >= 예산_min) & (apt_avg["평균매매가"] <= 예산_max)]

    if budget_apts.empty:
        st.warning(f"해당 예산 범위({fmt_price(예산_min)}~{fmt_price(예산_max)})에 맞는 아파트가 없습니다.")
    else:
        target_names = budget_apts["아파트"].tolist()
        target_trades = budget_df[budget_df["아파트"].isin(target_names)]

        # ── 지표 계산 ─────────────────────────────────────────────────
        score_df = budget_apts[["아파트", "평균매매가"]].copy()

        # 1) 평당가 (낮을수록 가성비 좋음)
        pyeong = target_trades.groupby("아파트")["평당가"].mean().reset_index(name="평당가")
        score_df = score_df.merge(pyeong, on="아파트", how="left")

        # 2) 전고점 대비 (낮을수록 저평가)
        all_max = target_trades.groupby("아파트")["매매가"].max().reset_index(name="전고점")
        last_m = target_trades["년월"].max()
        last_avg = (target_trades[target_trades["년월"] == last_m]
                    .groupby("아파트")["매매가"].mean().reset_index(name="최근가"))
        peak = all_max.merge(last_avg, on="아파트")
        peak["전고점대비"] = ((peak["최근가"] / peak["전고점"] - 1) * 100).round(1)
        score_df = score_df.merge(peak[["아파트", "전고점대비"]], on="아파트", how="left")

        # 3) 거래량 (많을수록 유동성 좋음)
        vol_score = target_trades.groupby("아파트").size().reset_index(name="거래건수")
        score_df = score_df.merge(vol_score, on="아파트", how="left")

        # 4) 수익률 (조회기간 내)
        fm = target_trades["년월"].min()
        lm = target_trades["년월"].max()
        first_avg = (target_trades[target_trades["년월"] == fm]
                     .groupby("아파트")["매매가"].mean().reset_index(name="시작가"))
        last_avg2 = (target_trades[target_trades["년월"] == lm]
                     .groupby("아파트")["매매가"].mean().reset_index(name="최근가2"))
        ret = first_avg.merge(last_avg2, on="아파트")
        ret["수익률"] = ((ret["최근가2"] / ret["시작가"] - 1) * 100).round(1)
        score_df = score_df.merge(ret[["아파트", "수익률"]], on="아파트", how="left")

        # 5) 전세가율 (낮을수록 안전) — 전세 데이터 있을 때만
        if not rent_df.empty:
            r_avg = rent_df[rent_df["아파트"].isin(target_names)].groupby("아파트")["전세가"].mean().reset_index(name="평균전세가")
            jeonse = score_df[["아파트", "평균매매가"]].merge(r_avg, on="아파트", how="left")
            jeonse["전세가율"] = (jeonse["평균전세가"] / jeonse["평균매매가"] * 100).round(1)
            score_df = score_df.merge(jeonse[["아파트", "전세가율"]], on="아파트", how="left")
        else:
            score_df["전세가율"] = None

        score_df = score_df.fillna(0)

        # ── 스코어링 (100점 만점) ──────────────────────────────────────
        def normalize(series, reverse=False):
            """0~1 정규화. reverse=True면 낮을수록 높은 점수"""
            s = series.astype(float)
            mn, mx = s.min(), s.max()
            if mx == mn:
                return pd.Series([0.5] * len(s), index=s.index)
            norm = (s - mn) / (mx - mn)
            return (1 - norm) if reverse else norm

        score_df["S_평당가"]    = normalize(score_df["평당가"], reverse=True) * 25
        score_df["S_전고점"]   = normalize(score_df["전고점대비"], reverse=True) * 20
        score_df["S_거래량"]   = normalize(score_df["거래건수"], reverse=False) * 15
        score_df["S_수익률"]   = normalize(score_df["수익률"], reverse=False) * 20

        if score_df["전세가율"].sum() > 0:
            score_df["S_전세가율"] = normalize(score_df["전세가율"], reverse=True) * 20
        else:
            score_df["S_전세가율"] = 10.0  # 데이터 없으면 중립

        score_df["종합점수"] = (
            score_df["S_평당가"] + score_df["S_전고점"] + score_df["S_거래량"]
            + score_df["S_수익률"] + score_df["S_전세가율"]
        ).round(1)

        score_df = score_df.sort_values("종합점수", ascending=False)

        # ── 스코어링 기준 안내 ─────────────────────────────────────────
        with st.expander("스코어링 기준 (100점 만점)", expanded=False):
            st.markdown("""
| 지표 | 배점 | 방향 | 설명 |
|------|------|------|------|
| **평당가** | 25점 | 낮을수록 높은 점수 | 같은 예산에 더 넓은 면적 = 가성비 |
| **전고점 대비** | 20점 | 낮을수록 높은 점수 | 전고점 대비 많이 빠진 = 저평가 가능성 |
| **수익률 추이** | 20점 | 높을수록 높은 점수 | 조회 기간 내 가격 상승세 |
| **전세가율** | 20점 | 낮을수록 높은 점수 | 전세가율 낮으면 안전 (갭투자 리스크 낮음) |
| **거래량** | 15점 | 많을수록 높은 점수 | 거래 활발 = 유동성 확보, 매도 용이 |
""")

        # ── 추천 결과 ──────────────────────────────────────────────────
        st.markdown(f"### 추천 결과 (총 {len(score_df)}개 단지)")

        # Top 3 카드
        top3 = score_df.head(3)
        medal = ["1위", "2위", "3위"]
        cols = st.columns(min(len(top3), 3))
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols[i]:
                st.markdown(f"**{medal[i]}**")
                st.metric(row["아파트"], f"{row['종합점수']:.0f}점")
                st.caption(
                    f"평균 {fmt_price(row['평균매매가'])}\n\n"
                    f"평당가 {row['평당가']:,.0f}만\n\n"
                    f"전고점대비 {row['전고점대비']:+.1f}%\n\n"
                    f"수익률 {row['수익률']:+.1f}%"
                )

        st.divider()

        # 전체 랭킹 테이블
        st.subheader("전체 랭킹")
        display_score = score_df.assign(
            평균매매가=score_df["평균매매가"].apply(fmt_price),
            평당가=score_df["평당가"].apply(lambda x: f"{x:,.0f}만원"),
            전고점대비=score_df["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
            수익률=score_df["수익률"].apply(lambda x: f"{x:+.1f}%"),
            전세가율=score_df["전세가율"].apply(lambda x: f"{x:.1f}%" if x > 0 else "-"),
            종합점수=score_df["종합점수"].apply(lambda x: f"{x:.0f}점"),
        )[["아파트", "평균매매가", "평당가", "전고점대비", "수익률", "전세가율", "거래건수", "종합점수"]]
        st.dataframe(display_score, use_container_width=True, hide_index=True)
