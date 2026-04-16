import streamlit as st
import pandas as pd
import sqlite3
import re

st.set_page_config(page_title="린나이 가격 모니터링", layout="wide")

st.markdown("""
<style>
    header {visibility: hidden;}
    .stAppToolbar {display: none;}
    [data-testid="stToolbar"] {display: none;}
    [data-testid="stHeader"] {display: none;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    #MainMenu {visibility: hidden;}

    .stApp { background-color: #f7f8fc; }
    .block-container {
        padding-top: 2rem;
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .header-box {
        background: #1e293b;
        border-radius: 16px;
        padding: 28px 32px;
        margin-bottom: 28px;
        color: white;
    }
    .header-title {
        font-size: 22px;
        font-weight: 700;
        margin: 0;
    }
    .header-sub {
        font-size: 13px;
        color: #94a3b8;
        margin-top: 6px;
    }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #e2e8f0;
        margin-bottom: 8px;
    }
    .metric-label {
        font-size: 12px;
        color: #94a3b8;
        margin-bottom: 8px;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .metric-value {
        font-size: 22px;
        font-weight: 800;
        color: #1e293b;
    }
    .metric-value.red { color: #ef4444; }
    .metric-value.green { color: #10b981; }

    .section-title {
        font-size: 14px;
        font-weight: 700;
        color: #64748b;
        margin: 24px 0 12px 0;
        letter-spacing: 0.5px;
    }

    .tbl {
        width: 100%;
        border-collapse: collapse;
        background: white;
        border-radius: 12px;
        overflow: hidden;
        font-family: sans-serif;
    }
    .tbl-head {
        display: grid;
        grid-template-columns: 1fr 1.5fr 1fr 0.8fr 1fr 1.2fr;
        background: #1e293b;
        color: white;
        padding: 13px 16px;
        font-size: 13px;
        font-weight: 600;
        border-radius: 12px 12px 0 0;
    }
    .tbl-row {
        display: grid;
        grid-template-columns: 1fr 1.5fr 1fr 0.8fr 1fr 1.2fr;
        padding: 12px 16px;
        font-size: 14px;
        color: #334155;
        border-bottom: 1px solid #f1f5f9;
        background: white;
    }
    .tbl-row.lowest {
        background: #fef2f2;
        color: #ef4444;
        font-weight: 700;
    }
    .tbl-row.company-rinnai-store {
        background: #fff7ed;
        color: #c2410c;
        font-weight: 700;
        border-left: 4px solid #f97316;
    }
    .tbl-row:hover { background: #f8fafc; }

    .badge {
        background: #ef4444;
        color: white;
        border-radius: 20px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 700;
        margin-left: 6px;
    }
    .company-badge {
        background: #f97316;
        color: white;
        border-radius: 20px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 700;
        margin-left: 6px;
    }

    .ship-free { color: #10b981; font-weight: 600; }
    .ship-paid { color: #f59e0b; font-weight: 600; }

    .change-up {
        background: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 10px;
        font-size: 14px;
        font-weight: 600;
    }
    .change-down {
        background: #ecfdf5;
        color: #059669;
        border: 1px solid #a7f3d0;
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 10px;
        font-size: 14px;
        font-weight: 600;
    }
    .change-time {
        font-size: 12px;
        opacity: 0.8;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


def get_data():
    conn = sqlite3.connect("rinnai_monitoring.db")
    try:
        df = pd.read_sql("SELECT * FROM price_comparison", conn)
        if not df.empty:
            latest_time = df["date"].max()
            df = df[df["date"] == latest_time].copy()
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


def get_price_changes():
    conn = sqlite3.connect("rinnai_monitoring.db")
    try:
        df = pd.read_sql("SELECT * FROM price_comparison ORDER BY id DESC", conn)
        if df.empty:
            return pd.DataFrame()

        changes = []

        grouped = df.groupby(["keyword", "mall_name"], sort=False)

        for (keyword, mall_name), group in grouped:
            group = group.sort_values("id", ascending=False).reset_index(drop=True)

            if len(group) < 2:
                continue

            latest = group.iloc[0]
            previous = group.iloc[1]

            old_total = int(previous["total_price"])
            new_total = int(latest["total_price"])

            if old_total != new_total:
                changes.append({
                    "keyword": latest["keyword"],
                    "mall_name": latest["mall_name"],
                    "old_total": old_total,
                    "new_total": new_total,
                    "diff": new_total - old_total,
                    "date": latest["date"]
                })

        return pd.DataFrame(changes)

    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def extract_model_id(keyword):
    parts = str(keyword).split()
    if len(parts) > 1 and parts[0] == "린나이":
        return parts[1]
    return parts[0] if parts else ""


def normalize_model_text(text):
    text = str(text).upper().strip()
    text = re.sub(r'[^A-Z0-9]', '', text)
    return text


def get_model_group_key(model_name):
    normalized = normalize_model_text(model_name)

    if normalized in ["M20G", "RFAM20G"]:
        return "GROUP_M20G"

    if normalized in ["M30G", "RFAM30G"]:
        return "GROUP_M30G"

    if normalized in ["RDT62RK", "RDT62RKW"]:
        return "GROUP_RDT62RK"

    if normalized == "RT6520I":
        return "GROUP_RT6520I"

    return f"MODEL_{normalized}"


def format_ship(x):
    try:
        val = int(x)
        if val == 0:
            return "<span class='ship-free'>무료</span>"
        return f"<span class='ship-paid'>{val:,}원</span>"
    except Exception:
        return f"<span class='ship-paid'>{str(x)}</span>"


st.button("새로고침", use_container_width=False)

latest_df = get_data()
changes_df = get_price_changes()


if not latest_df.empty:
    latest_collected_at = latest_df["date"].max()

    latest_df["model_name"] = latest_df["keyword"].apply(extract_model_id)
    latest_df["model_group_key"] = latest_df["model_name"].apply(get_model_group_key)

    group_label_df = (
        latest_df[["model_group_key", "model_name"]]
        .drop_duplicates(subset=["model_group_key"], keep="first")
        .copy()
    )

    ordered_group_keys = group_label_df["model_group_key"].tolist()
    model_label_map = dict(zip(group_label_df["model_group_key"], group_label_df["model_name"]))

    st.markdown(f"""
    <div class='header-box'>
        <div class='header-title'>린나이 대리점 가격 모니터링</div>
        <div class='header-sub'>📅 최종 수집: {latest_collected_at}</div>
    </div>
    """, unsafe_allow_html=True)

    if not changes_df.empty:
        st.markdown("<div class='section-title'>가격 변동 알림</div>", unsafe_allow_html=True)

        changes_df = changes_df.sort_values("date", ascending=False).reset_index(drop=True)

        for _, ch in changes_df.iterrows():
            model_name = extract_model_id(ch["keyword"])
            mall_name = ch["mall_name"]
            old_price = int(ch["old_total"])
            new_price = int(ch["new_total"])
            diff = int(ch["diff"])
            change_time = ch["date"]

            if diff > 0:
                st.markdown(
                    f"""
                    <div class='change-up'>
                        🔺 {mall_name} / {model_name} : {abs(diff):,}원 인상
                        <div class='change-time'>{old_price:,}원 → {new_price:,}원 · {change_time}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"""
                    <div class='change-down'>
                        🔻 {mall_name} / {model_name} : {abs(diff):,}원 인하
                        <div class='change-time'>{old_price:,}원 → {new_price:,}원 · {change_time}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    options = ["전체 보기"] + [model_label_map[k] for k in ordered_group_keys]
    selected_model = st.selectbox("모델 선택", options, label_visibility="collapsed")

    if selected_model == "전체 보기":
        view_df = latest_df.copy()
    else:
        selected_group_key = None
        for group_key in ordered_group_keys:
            if model_label_map[group_key] == selected_model:
                selected_group_key = group_key
                break

        if selected_group_key is None:
            view_df = pd.DataFrame()
        else:
            view_df = latest_df[latest_df["model_group_key"] == selected_group_key].copy()

    if not view_df.empty:
        view_df = view_df.sort_values("total_price").reset_index(drop=True)

        min_total = int(view_df["total_price"].min())
        max_total = int(view_df["total_price"].max())
        avg_total = int(view_df["total_price"].mean())
        count = len(view_df)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f"""<div class='metric-card'><div class='metric-label'>최저가</div><div class='metric-value red'>{min_total:,}원</div></div>""",
                unsafe_allow_html=True
            )
        with c2:
            st.markdown(
                f"""<div class='metric-card'><div class='metric-label'>최고가</div><div class='metric-value'>{max_total:,}원</div></div>""",
                unsafe_allow_html=True
            )
        with c3:
            st.markdown(
                f"""<div class='metric-card'><div class='metric-label'>평균가</div><div class='metric-value green'>{avg_total:,}원</div></div>""",
                unsafe_allow_html=True
            )
        with c4:
            st.markdown(
                f"""<div class='metric-card'><div class='metric-label'>수집 건수</div><div class='metric-value'>{count}건</div></div>""",
                unsafe_allow_html=True
            )

        st.markdown("<div class='section-title'>대리점별 가격 목록 · 낮은 가격순</div>", unsafe_allow_html=True)

        rows_html = """<div class='tbl-head'>
            <div>제품명</div><div>판매처</div><div>제품 금액</div><div>배송비</div><div>합산 금액</div><div>수집 시각</div>
        </div>"""

        for _, row in view_df.iterrows():
            model = row["model_name"]
            mall = row["mall_name"]
            sell = int(row["sell_price"])
            ship_html = format_ship(row["ship_fee"])
            total = int(row["total_price"])
            date = row["date"]

            is_lowest = total == min_total
            is_our_company = str(mall).strip() == "린나이스토어"

            row_classes = ["tbl-row"]
            if is_lowest:
                row_classes.append("lowest")
            if is_our_company:
                row_classes.append("company-rinnai-store")

            row_class = " ".join(row_classes)

            badges = []
            if is_lowest:
                badges.append("<span class='badge'>최저가</span>")
            if is_our_company:
                badges.append("<span class='company-badge'>우리회사</span>")

            badge_html = "".join(badges)

            rows_html += f"""<div class='{row_class}'>
                <div>{model}</div>
                <div>{mall}{badge_html}</div>
                <div>{sell:,}원</div>
                <div>{ship_html}</div>
                <div>{total:,}원</div>
                <div style='font-size:12px; color:#94a3b8;'>{date}</div>
            </div>"""

        st.markdown(f"<div class='tbl'>{rows_html}</div>", unsafe_allow_html=True)
    else:
        st.info("선택한 모델에 해당하는 데이터가 없습니다.")

else:
    st.warning("⚠️ 표시할 데이터가 없습니다. 수집기를 먼저 실행해 주세요.")

