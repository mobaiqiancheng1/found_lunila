# ============================
# 0. 基础库导入（已集成 Supabase）
# ============================
import streamlit as st
import pandas as pd
import os
import time
import requests
import json
from openai import OpenAI
from supabase import create_client, Client
import numpy as np

# ============================
# 1. API 配置（从环境变量安全读取）
# ============================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-d184d099b07c41e9951000e8dd3b464e")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 安全检查：Supabase 凭据必须存在
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ 未配置 Supabase 凭据！请在 Streamlit Cloud Settings → Secrets 中添加：\nSUPABASE_URL 和 SUPABASE_KEY")
    st.stop()

# 初始化 Supabase 客户端
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Supabase 连接失败: {str(e)}\n请检查 Secrets 配置是否正确")
    st.stop()

# ============================
# 2. Supabase 数据操作函数（核心替换）
# ============================
def load_portfolio(username: str) -> pd.DataFrame:
    """从 Supabase 加载用户持仓数据"""
    try:
        response = supabase.table("portfolios").select("*").eq("username", username).execute()
        if not response.data:
            return pd.DataFrame(columns=["基金代码", "基金名称", "持有份额", "成本单价"])
        
        # 转换并重命名列
        df = pd.DataFrame(response.data)
        df = df.rename(columns={
            "fund_code": "基金代码",
            "fund_name": "基金名称",
            "shares": "持有份额",
            "cost_price": "成本单价"
        })
        # 确保列顺序和类型
        df = df[["基金代码", "基金名称", "持有份额", "成本单价"]].copy()
        df["持有份额"] = pd.to_numeric(df["持有份额"], errors='coerce').fillna(0)
        df["成本单价"] = pd.to_numeric(df["成本单价"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"⚠️ 加载 {username} 的持仓失败: {str(e)}")
        return pd.DataFrame(columns=["基金代码", "基金名称", "持有份额", "成本单价"])

def save_portfolio(username: str, df: pd.DataFrame) -> bool:
    """保存持仓到 Supabase（覆盖式更新）"""
    try:
        # 1. 删除该用户所有旧记录
        supabase.table("portfolios").delete().eq("username", username).execute()
        
        # 2. 准备新记录（仅保留必要列）
        if df.empty:
            return True
            
        records = df[["基金代码", "基金名称", "持有份额", "成本单价"]].rename(columns={
            "基金代码": "fund_code",
            "基金名称": "fund_name",
            "持有份额": "shares",
            "成本单价": "cost_price"
        }).to_dict('records')
        
        # 3. 添加用户名并插入
        for record in records:
            record["username"] = username
            # 确保数值类型
            record["shares"] = float(record["shares"]) if record["shares"] else 0.0
            record["cost_price"] = float(record["cost_price"]) if record["cost_price"] else 0.0
        
        if records:
            supabase.table("portfolios").upsert(records).execute()
        return True
    except Exception as e:
        st.error(f"❌ 保存 {username} 的持仓失败: {str(e)}")
        return False

# ============================
# 3. 页面基础配置
# ============================
st.set_page_config(
    page_title="噜咪啦基金助手",
    layout="wide",
    page_icon="📈"
)

# ============================
# 4. UI 样式引擎（CSS 强制注入）
# ============================
st.markdown("""
<style>
    .stApp { background-color: #FFCCCC !important; }
    .hero-card {
        border-radius: 20px !important;
        padding: 30px 15px !important;
        text-align: center !important;
        box-shadow: 0 8px 20px rgba(0,0,0,0.3) !important;
        margin-bottom: 25px !important;
    }
    .card-cyan { background-color: #CCFFFF !important; color: #1A1A1A !important; }
    .card-blue { background-color: #99CCFF !important; color: #1A1A1A !important; }
    .card-yellow { background-color: #FFFFCC !important; color: #1A1A1A !important; }
    .card-label { font-size: 1rem !important; font-weight: bold !important; opacity: 0.8 !important; }
    .card-value { font-size: 2.5rem !important; font-weight: 900 !important; }
    
    [data-testid="stSidebar"] { background-color: #F0F8FF !important; border-right: 2px solid #E6F0FF !important; }
    [data-testid="stSidebar"] [data-baseweb="accordion"] { background-color: #E6F0FF !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

# ============================
# 5. 基金行情抓取函数（保持不变）
# ============================
@st.cache_data(ttl=60)
def fetch_fund_data(code):
    code = str(code).zfill(6)
    try:
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        r = requests.get(url, timeout=3)
        if "jsonpgz" in r.text:
            data = json.loads(r.text[r.text.find('{'):r.text.rfind('}') + 1])
            return (
                float(data['dwjz']),
                float(data['gsz']),
                float(data['gszzl']),
                data['name'],
                data['jzrq'],
                True
            )
    except:
        pass
    return 1.0, 1.0, 0.0, "未找到", "-", False

# ============================
# 6. 侧边栏：持仓管理（Supabase 集成版）
# ============================
with st.sidebar:
    st.markdown("## 👤 账户切换")
    user_list = ["噜噜", "咪咪"]
    history_profit_patch = st.number_input("🛠️ 历史盈亏修正总额", value=0.0)
    current_user = st.selectbox("选择当前查看的账户", user_list)
    
    # ✅ 关键替换：不再使用本地文件，直接加载 Supabase 数据
    df_db = load_portfolio(current_user)
    st.info(f"☁️ 当前查看: **{current_user}** 的云端持仓 | 记录数: {len(df_db)}")
    st.markdown("---")

# --- 快捷添加新持仓 ---
with st.sidebar:
    st.markdown("### 📝 资产管理面板")
    
    with st.expander("➕ 快捷添加新持仓", expanded=False):
        def auto_fill_name():
            code = st.session_state.get("add_code", "")
            if code and len(code) == 6:
                _, _, _, nm, _, ok = fetch_fund_data(code)
                if ok:
                    st.session_state.add_name = nm
                else:
                    st.toast(f"未找到代码 {code} 的信息", icon="⚠️")

        in_code = st.text_input("基金代码 (6位)", key="add_code", on_change=auto_fill_name)
        f_name = st.text_input("确认名称", key="add_name")
        f_cost = st.number_input("持仓成本单价", format="%.4f", key="add_cost")
        f_share = st.number_input("持有份额", format="%.2f", key="add_share")

        if st.button("🚀 初始入库", use_container_width=True):
            if f_name and f_share > 0 and in_code:
                # 读取当前数据 → 添加新行 → 保存
                current_df = load_portfolio(current_user)
                new_row = pd.DataFrame([{
                    "基金代码": in_code.zfill(6),
                    "基金名称": f_name,
                    "持有份额": f_share,
                    "成本单价": f_cost
                }])
                updated_df = pd.concat([current_df, new_row], ignore_index=True)
                if save_portfolio(current_user, updated_df):
                    st.success(f"✅ 已存入云端: {f_name}")
                    time.sleep(1)
                    st.rerun()

# --- 存量交易管理 ---
with st.sidebar:
    with st.expander("🔄 存量交易管理 (买入/卖出)", expanded=True):
        def get_history_nav(code, date_str):
            try:
                ts = int(time.time() * 1000)
                url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=1&startDate={date_str}&endDate={date_str}&_={ts}"
                headers = {"Referer": "http://fundf10.eastmoney.com/"}
                r = requests.get(url, headers=headers, timeout=2)
                data = r.json()
                if data['Data']['LSJZList']:
                    return float(data['Data']['LSJZList'][0]['DWJZ'])
            except:
                pass
            return 0.0

        if not df_db.empty:
            fund_options = df_db.apply(lambda x: f"{x['基金代码']} - {x['基金名称']}", axis=1).tolist()
            trade_target = st.selectbox("选择操作基金", fund_options)
            trade_code = trade_target.split(" - ")[0]

            c_date, c_type = st.columns([1.5, 1])
            with c_date:
                trade_date = st.date_input("📅 交易/净值日期", value="today")
            with c_type:
                t_type = st.radio("动作", ["买入", "卖出"], horizontal=True, label_visibility="collapsed")

            st.write("---")

            r1_col1, r1_col2 = st.columns([1.8, 1])
            with r1_col1:
                t_amount = st.number_input("💰 交易金额 (元)", min_value=0.0, step=100.0, format="%.2f")
            with r1_col2:
                st.write(" ")
                if st.button("🔍 抓取", use_container_width=True):
                    fetched_nav = get_history_nav(trade_code, str(trade_date))
                    if fetched_nav > 0:
                        st.session_state[f"nav_{trade_code}"] = fetched_nav
                        st.toast(f"✅ 获取 {trade_date} 净值: {fetched_nav:.4f}")
                    else:
                        st.toast("⚠️ 未查到净值，请手动输入", icon="⚠️")

            r2_col1, r2_col2 = st.columns(2)
            with r2_col1:
                default_nav = st.session_state.get(f"nav_{trade_code}", 1.0000)
                t_price = st.number_input("📉 确认净值", value=default_nav, format="%.4f", step=0.0001)
            with r2_col2:
                calc_share = t_amount / t_price if t_price > 0 else 0.00
                st.text_input("🍰 确认份额", value=f"{calc_share:,.2f}", disabled=True)

            if st.button("🚀 确认提交交易", use_container_width=True):
                if t_amount > 0 and t_price > 0:
                    current_df = load_portfolio(current_user)
                    rows = current_df[current_df['基金代码'] == trade_code]
                    if rows.empty:
                        st.error("❌ 未找到该基金记录")
                        st.stop()
                    idx = rows.index[0]

                    old_share = float(current_df.at[idx, '持有份额'])
                    old_cost = float(current_df.at[idx, '成本单价'])
                    calc_share = t_amount / t_price

                    if t_type == "买入":
                        new_share_part = calc_share
                        new_total_share = old_share + new_share_part
                        new_avg_cost = ((old_share * old_cost) + t_amount) / new_total_share
                        current_df.at[idx, '持有份额'] = new_total_share
                        current_df.at[idx, '成本单价'] = new_avg_cost
                        if save_portfolio(current_user, current_df):
                            st.success(f"✅ 加仓成功！份额 +{new_share_part:.2f}")
                            time.sleep(1)
                            st.rerun()
                    else:  # 卖出
                        if calc_share > old_share + 0.01:
                            st.error(f"❌ 份额不足！需卖出 {calc_share:.2f}，但你只有 {old_share:.2f}")
                            st.stop()
                        remain = old_share - calc_share
                        if remain < 0.01:
                            current_df.at[idx, '持有份额'] = 0.0
                            st.success("🎉 已全额卖出！记录已保留（份额=0）")
                        else:
                            current_df.at[idx, '持有份额'] = remain
                            st.success(f"✅ 减仓成功！份额减少 {calc_share:.2f}")
                        if save_portfolio(current_user, current_df):
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("💡 请先添加持仓记录")

# ============================
# 7. 核心收益计算逻辑（使用云端数据）
# ============================
view_data = []
total_v = 0.0
total_d = 0.0
total_h = 0.0

if not df_db.empty:
    temp_list = []
    for _, row in df_db.iterrows():
        dwjz, gsz, zf, nm, jzrq, ok = fetch_fund_data(row['基金代码'])
        share = float(row['持有份额'])
        cost = float(row['成本单价'])
        
        # 跳过份额为0的记录（已清仓）
        if share < 0.01:
            continue
            
        yest_val = share * dwjz
        day_inc = yest_val * (zf / 100)
        hold_inc = (gsz - cost) * share

        total_v += yest_val
        total_d += day_inc
        total_h += hold_inc

        temp_list.append({
            "代码": row['基金代码'], "基金名称": nm, "持有金额": yest_val,
            "涨幅": zf, "当日收益": day_inc, "累计收益": hold_inc, "成本": cost, "现价": gsz
        })

    for item in temp_list:
        portion = (item['持有金额'] / total_v * 100) if total_v > 0 else 0
        rate = ((item['现价'] - item['成本']) / (item['成本'] + 1e-6) * 100)
        view_data.append({
            "选": False,
            "代码": item['代码'],
            "基金名称": item['基金名称'],
            "占比": round(portion, 2),
            "持有金额": round(item['持有金额'], 2),
            "涨幅": round(item['涨幅'], 2),
            "当日收益": round(item['当日收益'], 2),
            "累计收益": round(item['累计收益'], 2),
            "收益率": round(rate, 2)
        })

# ============================
# 8. AI 聊天初始化
# ============================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_chat" not in st.session_state:
    st.session_state.show_chat = False

# ============================
# 9. 主界面逻辑
# ============================
with st.sidebar:
    st.markdown("---")
    if st.button(
        "💬 召唤 咪咪小天才" if not st.session_state.show_chat else "❌ 关闭 咪咪小天才",
        use_container_width=True
    ):
        st.session_state.show_chat = not st.session_state.show_chat
        st.rerun()
    if st.button("🧹 清空对话历史", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# 动态布局
if st.session_state.show_chat:
    col_main, col_ai = st.columns([3, 1])
else:
    col_main = st.container()

# --- 主看板 ---
with col_main:
    st.title("📈 噜咪啦基金助手 (云端版)")
    
    # 指标卡片
    mc1, mc2, mc3 = st.columns(3)
    mc1.markdown(
        f'<div class="hero-card card-cyan"><div class="card-label">💰 总资产</div><div class="card-value">¥{total_v:,.2f}</div></div>',
        unsafe_allow_html=True)
    mc2.markdown(
        f'<div class="hero-card card-blue"><div class="card-label">📊 当日盈亏</div><div class="card-value">¥{total_d:+,.2f}</div></div>',
        unsafe_allow_html=True)
    final_profit_display = total_h + history_profit_patch
    mc3.markdown(
        f'<div class="hero-card card-yellow"><div class="card-label">🏆 累计盈亏</div><div class="card-value">¥{final_profit_display:+,.2f}</div></div>',
        unsafe_allow_html=True)

    # 持仓明细
    st.markdown('<div class="quant-board">', unsafe_allow_html=True)
    st.markdown("<h3>📋 持仓明细 (云端同步)</h3>", unsafe_allow_html=True)
    
    ca, cb = st.columns([1, 1])
    with ca:
        if st.button("🔄 同步行情"):
            st.cache_data.clear()
            st.rerun()
    with cb:
        btn_del = st.button("🗑️ 移除选中记录")

    if view_data:
        df_view = pd.DataFrame(view_data)
        ROW_HEIGHT = 35
        HEADER_HEIGHT = 40
        MAX_HEIGHT = 900
        table_height = min(HEADER_HEIGHT + ROW_HEIGHT * len(df_view), MAX_HEIGHT)
        
        edited_df = st.data_editor(
            df_view,
            hide_index=True,
            use_container_width=True,
            column_config={
                "选": st.column_config.CheckboxColumn(width="small"),
                "持有金额": st.column_config.NumberColumn(format="¥%.2f"),
                "占比": st.column_config.ProgressColumn("持仓占比", format="%.2f%%", min_value=0, max_value=100),
                "涨幅": st.column_config.NumberColumn("实时涨跌", format="%+.2f%%"),
                "当日收益": st.column_config.NumberColumn(format="¥%+.2f"),
                "累计收益": st.column_config.NumberColumn(format="¥%+.2f"),
                "收益率": st.column_config.NumberColumn(format="%+.2f%%"),
            },
            height=table_height
        )
        
        # 删除选中记录（关键替换）
        if btn_del:
            to_del = edited_df[edited_df["选"] == True]["代码"].tolist()
            if to_del:
                updated_df = df_db[~df_db["基金代码"].isin(to_del)]
                if save_portfolio(current_user, updated_df):
                    st.success(f"✅ 已从云端移除 {len(to_del)} 条记录")
                    time.sleep(1)
                    st.rerun()
    else:
        st.info("💡 暂无持仓数据，请在侧边栏添加")
    st.markdown('</div>', unsafe_allow_html=True)

# --- AI 对话窗口 ---
if st.session_state.show_chat:
    with col_ai:
        st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)
        st.markdown("""
            <div style="background-color: rgba(255,255,255,0.5); padding: 6px; border-radius: 10px; border: 1px solid #E6F0FF;">
                <h3 style="color: #1A5276; margin-top:0;">🤖 聪明的咪咪 (云端数据)</h3>
            </div>
        """, unsafe_allow_html=True)
        
        chat_container = st.container(height=500)
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        
        if prompt := st.chat_input("询问持仓建议..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
            
            try:
                client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
                fund_context = f"用户 {current_user} 的持仓: {view_data}"
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": f"你是专业基金助手，分析 {current_user} 的资产。数据: {fund_context}"},
                        *st.session_state.messages
                    ]
                )
                answer = response.choices[0].message.content
                with chat_container:
                    with st.chat_message("assistant"):
                        st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error("⚠️ AI 服务暂时不可用，请稍后再试")

# ============================
# 10. 页脚提示（增强用户体验）
# ============================
st.markdown("---")
st.caption("☁️ 数据已安全存储至 Supabase 云端 | 刷新页面数据不丢失 | 多设备同步查看")
