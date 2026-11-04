import streamlit as st
import pandas as pd
import plotly.express as px

# 1. 頁面基本配置
st.set_page_config(page_title="檔案時間趨勢分析工具", layout="wide")
st.title("📈 數據檔案時間序列分析工具")
st.caption("支援上傳 .xlsx, .xls, .csv 與各類分隔符號的 .txt 檔")

# 2. 檔案上傳元件
uploaded_file = st.file_uploader(
    "請選擇或拖曳檔案至此",
    type=["xlsx", "xls", "csv", "txt"]
)

if uploaded_file is not None:
    try:
        # 自動根據副檔名判定讀取方式
        if uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            # 支援逗號、Tab、空格等多種分隔符號的 TXT / CSV
            df = pd.read_csv(uploaded_file, sep=None, engine='python')

        st.success(f"成功讀取檔案：{uploaded_file.name}（共 {len(df)} 筆資料、{len(df.columns)} 個欄位）")

        # 展開預覽原始資料
        with st.expander("🔍 預覽前 5 筆原始資料"):
            st.dataframe(df.head())

        columns = list(df.columns)

        # 3. 欄位選擇介面
        col_left, col_right = st.columns(2)
        with col_left:
            time_col = st.selectbox("選擇【時間 / 日期】欄位：", columns)
        with col_right:
            value_cols = st.multiselect(
                "選擇要分析的【數值】欄位（可多選）：",
                [c for c in columns if c != time_col]
            )

        # 4. 資料清理與繪圖
        if time_col and value_cols:
            # 時間格式轉換與數值防呆
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
            for col in value_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # 排除無效值並依時間由舊到新排序
            valid_df = df.dropna(subset=[time_col] + value_cols).sort_values(by=time_col)

            if valid_df.empty:
                st.warning("⚠️ 所選欄位清理後沒有可用的完整資料，請確認時間與數值格式。")
            else:
                # 使用 Plotly 繪製互動式圖表
                fig = px.line(
                    valid_df,
                    x=time_col,
                    y=value_cols,
                    markers=True,
                    title=f"時間趨勢圖（{', '.join(value_cols)}）",
                    labels={time_col: "時間", "value": "數值", "variable": "指標"}
                )

                # 圖表互動樣式設定
                fig.update_layout(
                    hovermode="x unified",
                    xaxis_title="時間",
                    yaxis_title="數值",
                    legend_title_text="指標名稱"
                )

                # 在網頁上呈現圖表
                st.plotly_chart(fig, use_container_width=True)

        elif not value_cols:
            st.info("請在上方選擇至少一個數值欄位以產生圖表。")

    except Exception as e:
        st.error(f"檔案解析失敗，錯誤原因：{e}")