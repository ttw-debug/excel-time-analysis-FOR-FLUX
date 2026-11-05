import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 頁面配置
st.set_page_config(page_title="批次時間序列分析工具", layout="wide")
st.title("📈 多檔案批次時間序列分析工具")
st.caption("支援一次上傳整月（多個同格式）檔案，自動縱向拼接、時間排序並繪製長期趨勢圖。")

# 2. 多檔案上傳元件 (開啟 accept_multiple_files)
uploaded_files = st.file_uploader(
    "請選取或框選拖曳整月份的所有檔案（可一次選取數十個檔案）：",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True
)

if uploaded_files:
    df_list = []
    error_files = []

    # 批次讀取與進度條反饋
    with st.status(f"正在批次解析 {len(uploaded_files)} 份檔案...", expanded=False) as status:
        for file in uploaded_files:
            try:
                if file.name.endswith(('.xlsx', '.xls')):
                    temp_df = pd.read_excel(file)
                else:
                    # 自動適應 tab、逗號或空白分隔的 TXT/CSV
                    temp_df = pd.read_csv(file, sep=None, engine='python')
                
                # 附加原始檔名方便追蹤來源
                temp_df["_source_file"] = file.name
                df_list.append(temp_df)
            except Exception as e:
                error_files.append((file.name, str(e)))

        if error_files:
            st.warning(f"⚠️ 共有 {len(error_files)} 份檔案讀取失敗並已跳過。")
        status.update(label=f"✅ 成功載入 {len(df_list)} 份檔案！", state="complete")

    if df_list:
        # 縱向拼接所有檔案資料
        raw_df = pd.concat(df_list, ignore_index=True)

        st.success(f"整月資料彙整完成：共合併 {len(df_list)} 個檔案，累計 {len(raw_df):,} 筆資料、{len(raw_df.columns)-1} 個數據欄位。")

        with st.expander("🔍 檢視合併後的資料前 5 筆與後 5 筆"):
            st.dataframe(pd.concat([raw_df.head(5), raw_df.tail(5)]))

        columns = [c for c in raw_df.columns if c != "_source_file"]

        # 3. 欄位設定
        col1, col2 = st.columns(2)
        with col1:
            time_col = st.selectbox("選擇【時間 / 日期】欄位：", columns)
        with col2:
            value_cols = st.multiselect(
                "選擇要分析的【數值】欄位（可多選）：",
                [c for c in columns if c != time_col]
            )

        # 4. 資料清理、去重與繪圖
        if time_col and value_cols:
            df_plot = raw_df.copy()
            
            # 時間格式轉換
            df_plot[time_col] = pd.to_datetime(df_plot[time_col], errors='coerce')
            
            # 數值型別防呆轉換
            for col in value_cols:
                df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce')

            # 排除時間或目標數值為 NaN 的無效列
            df_plot = df_plot.dropna(subset=[time_col] + value_cols)

            # 依時間順序升冪排列，並排除跨日重複記錄（若有重複保留最後一筆）
            df_plot = df_plot.sort_values(by=time_col).drop_duplicates(subset=[time_col], keep='last')

            if df_plot.empty:
                st.warning("⚠️ 篩選後無有效數據，請確認時間與數值內容格式。")
            else:
                total_points = len(df_plot)
                start_time = df_plot[time_col].min().strftime('%Y-%m-%d %H:%M')
                end_time = df_plot[time_col].max().strftime('%Y-%m-%d %H:%M')
                
                st.info(f"📊 分析區間：`{start_time}` 至 `{end_time}`（總計有效點數：{total_points:,} 點）")

                # 資料量大時自動隱藏圓點標記以提升瀏覽器流暢度
                show_markers = True if total_points <= 500 else False

                fig = px.line(
                    df_plot,
                    x=time_col,
                    y=value_cols,
                    markers=show_markers,
                    title=f"整月時間趨勢分析（{start_time} ~ {end_time}）",
                    labels={time_col: "時間", "value": "數值", "variable": "指標"}
                )

                fig.update_layout(
                    hovermode="x unified",
                    xaxis_title="時間",
                    yaxis_title="數值",
                    legend_title_text="指標名稱"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 5. 額外功能：提供整月份清洗合併後資料下載
                st.divider()
                csv_buffer = io.BytesIO()
                df_plot.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 下載整月份合併清洗後的 CSV 檔案",
                    data=csv_buffer.getvalue(),
                    file_name=f"merged_month_{df_plot[time_col].dt.strftime('%Y%m').iloc[0]}.csv",
                    mime="text/csv"
                )

        elif not value_cols:
            st.info("請於上方選取至少一個欲觀察的數值欄位。")
