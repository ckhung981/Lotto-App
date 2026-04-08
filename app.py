import os
import io
import time
import zipfile
import requests
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st

# --- 頁面設定 ---
st.set_page_config(page_title="大樂透加權產生器", page_icon="🎰", layout="centered")

MASTER_CSV = 'lotto_master.csv'

# ==========================================
# 1. 核心解析模組 (修復空欄位位移問題)
# ==========================================
def fetch_year_data(year):
    zip_url = f"https://cdn.taiwanlottery.com.tw/app/FilesForDownload/Download/LottoResult/{year}.zip"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0'}
    try:
        r = requests.get(zip_url, headers=headers, timeout=10)
        if r.status_code != 200: return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for info in z.infolist():
                try:
                    correct_name = info.filename.encode('cp437').decode('big5')
                except:
                    correct_name = info.filename
                
                if f"大樂透_{year}" in correct_name:
                    content = z.read(info.filename)
                    text = content.decode('cp950', errors='ignore')
                    
                    temp_df = pd.read_csv(io.StringIO(text), skiprows=1, header=None)
                    temp_df = temp_df.dropna(axis=1, how='all')
                    temp_df.columns = range(temp_df.shape[1])
                    
                    final_df = pd.DataFrame()
                    final_df['開獎日期'] = pd.to_datetime(temp_df[2], errors='coerce')
                    final_df['期別'] = temp_df[1]
                    for i in range(6):
                        final_df[f'獎號{i+1}'] = pd.to_numeric(temp_df[6+i], errors='coerce')
                    final_df['特別號'] = pd.to_numeric(temp_df[12], errors='coerce')
                    
                    return final_df.dropna(subset=['開獎日期']).reset_index(drop=True)
    except Exception as e:
        pass
    return None

# ==========================================
# 2. 智慧增量更新
# ==========================================
def smart_update_database():
    current_year = datetime.datetime.now().year
    progress_text = "正在連線台彩伺服器更新資料..."
    my_bar = st.progress(0, text=progress_text)
    
    if not os.path.exists(MASTER_CSV):
        all_data = []
        years_to_fetch = list(range(2007, current_year + 1))
        total_years = len(years_to_fetch)
        
        for i, y in enumerate(years_to_fetch):
            my_bar.progress((i + 1) / total_years, text=f"正在下載 {y} 年歷史資料...")
            df = fetch_year_data(y)
            if df is not None: all_data.append(df)
            time.sleep(0.5)
            
        master_df = pd.concat(all_data, ignore_index=True)
    else:
        my_bar.progress(50, text=f"正在檢查 {current_year} 年最新開獎紀錄...")
        master_df = pd.read_csv(MASTER_CSV)
        master_df['開獎日期'] = pd.to_datetime(master_df['開獎日期'])
        master_df = master_df[master_df['開獎日期'].dt.year != current_year]
        
        current_year_df = fetch_year_data(current_year)
        if current_year_df is not None:
            master_df = pd.concat([master_df, current_year_df], ignore_index=True)
            
        my_bar.progress(100, text="更新完成！")
            
    master_df = master_df.sort_values(by='開獎日期', ascending=False).reset_index(drop=True)
    master_df.to_csv(MASTER_CSV, index=False)
    time.sleep(1)
    my_bar.empty()
    return master_df

# ==========================================
# 3. 繪圖與產生號碼 (支援動態標題)
# ==========================================
def create_stats_plot_and_generate(filtered_df, start_str, end_str):
    number_cols = ['獎號1', '獎號2', '獎號3', '獎號4', '獎號5', '獎號6', '特別號']
    stats_df = filtered_df[number_cols].stack().value_counts().reset_index()
    stats_df.columns = ['號碼', '出現次數']
    stats_df['號碼'] = stats_df['號碼'].astype(int)
    stats_df = stats_df.sort_values(by='號碼')

    # 抽籤
    numbers = stats_df['號碼'].values
    probs = stats_df['出現次數'].values / stats_df['出現次數'].sum()
    drawn = np.random.choice(numbers, size=7, replace=False, p=probs)
    reg = [f"{n:02d}" for n in sorted(drawn[:6])]
    spec = f"{drawn[6]:02d}"

    # 繪圖
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(12, 5))
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False

    sns.barplot(x='號碼', y='出現次數', data=stats_df, palette='viridis', ax=ax)
    avg_freq = stats_df['出現次數'].mean()
    ax.axhline(avg_freq, color='red', linestyle='--', label=f'平均次數: {avg_freq:.2f}')
    
    # 圖表標題動態顯示使用者選擇的區間
    ax.set_title(f'大樂透歷史號碼頻率統計 ({start_str} 至 {end_str})', fontsize=14)
    ax.set_xlabel('號碼', fontsize=10)
    ax.set_ylabel('出現總次數', fontsize=10)
    ax.legend()
    plt.xticks(rotation=45)
    
    return reg, spec, fig

# ==========================================
# 4. Streamlit UI 介面設計
# ==========================================
st.title("🎰 大樂透智慧加權產生器")
st.write("根據真實開獎機率，為您產生專屬投注號碼。")

# --- 側邊欄：系統操作與過濾器 ---
with st.sidebar:
    st.header("⚙️ 資料庫管理")
    
    # 功能 1：一般智慧更新 (只抓今年)
    if st.button("🔄 智慧更新資料庫 (增量)", use_container_width=True):
        st.session_state.master_df = smart_update_database()
        st.success("資料庫已更新至最新期數！")
        
    # 功能 2：強制修復/重新下載
    if st.button("⚠️ 強制重新下載 (修復損壞)", type="primary", use_container_width=True, help="如果發生錯誤或資料對不上，點此重新抓取2007年至今的所有資料。"):
        if os.path.exists(MASTER_CSV):
            os.remove(MASTER_CSV) # 先刪除壞掉的檔案
        st.session_state.master_df = smart_update_database()
        st.success("資料庫已完全重建！")

# --- 讀取資料庫 ---
if 'master_df' not in st.session_state:
    if os.path.exists(MASTER_CSV):
        df = pd.read_csv(MASTER_CSV)
        df['開獎日期'] = pd.to_datetime(df['開獎日期'])
        st.session_state.master_df = df
    else:
        st.session_state.master_df = None

# --- 主畫面邏輯 ---
if st.session_state.master_df is not None:
    df = st.session_state.master_df
    
    # 取得資料庫的最早與最晚日期
    min_date = df['開獎日期'].min().date()
    max_date = df['開獎日期'].max().date()
    
    # 側邊欄：自訂計算區間 (功能 3)
    with st.sidebar:
        st.markdown("---")
        st.header("📅 自訂權重計算區間")
        start_date = st.date_input("開始日期", min_date, min_value=min_date, max_value=max_date)
        end_date = st.date_input("結束日期", max_date, min_value=min_date, max_value=max_date)

    if start_date > end_date:
        st.error("❌ 結束日期必須晚於開始日期！請重新選擇。")
    else:
        # 根據使用者選擇過濾資料
        mask = (df['開獎日期'].dt.date >= start_date) & (df['開獎日期'].dt.date <= end_date)
        filtered_df = df.loc[mask]
        
        if len(filtered_df) == 0:
            st.warning("⚠️ 在您選擇的日期區間內，沒有任何開獎紀錄，請擴大範圍。")
        else:
            # 顯示資訊面板
            latest_date_str = filtered_df['開獎日期'].max().strftime('%Y-%m-%d')
            st.info(f"📊 所選區間共計 **{len(filtered_df)}** 期 (最新開獎: {latest_date_str})")
            st.markdown("---")
            
            # 產生號碼大按鈕
            if st.button("🚀 點我產生本期推薦號碼", type="primary", use_container_width=True):
                with st.spinner("🎲 正在根據選定區間的歷史機率轉動彩球..."):
                    time.sleep(1) # 增加期待感
                    
                    # 傳入過濾後的資料與日期字串
                    reg, spec, fig = create_stats_plot_and_generate(
                        filtered_df, 
                        start_date.strftime('%Y-%m'), 
                        end_date.strftime('%Y-%m')
                    )
                    
                    st.success("✨ 號碼產生成功！祝您中大獎！")
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.metric(label="一般號碼 (6碼)", value=" - ".join(reg))
                    with col2:
                        st.metric(label="特別號", value=spec)
                    
                    st.markdown(f"### 📈 {start_date.strftime('%Y')} ~ {end_date.strftime('%Y')} 權重分佈圖")
                    st.pyplot(fig)

else:
    st.warning("⚠️ 找不到歷史資料庫，請先點擊左側欄的「智慧更新資料庫」進行初次下載。")