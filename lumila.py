# ============================
# 0. 基础库导入
# ============================
import streamlit as st  # Streamlit：用于快速构建 Web 应用
import pandas as pd  # Pandas：数据表处理
import os  # OS：文件路径与文件存在性判断
import time  # 时间模块（此版本中未直接使用，可扩展）
import requests  # HTTP 请求，用于获取基金实时数据
import json  # JSON 解析
from openai import OpenAI  # OpenAI SDK（此处用于 DeepSeek 接口）
from st_supabase_connection import SupabaseConnection # 新增这一行

# ============================
# 1. API 密钥配置（已内置）
# ============================
# DeepSeek API Key（⚠️正式部署建议使用环境变量）
DEEPSEEK_API_KEY = "sk-d184d099b07c41e9951000e8dd3b464e"

# ============================
# 2. 页面基础配置
# ============================
# 设置网页标题、布局方式、浏览器标签页图标
st.set_page_config(
    page_title="噜咪啦基金助手",
    layout="wide",  # 宽屏布局
    page_icon="📈"
)

# ============================
# 3. UI 样式引擎（CSS 强制注入 - 深度修复版）
# ============================
# 使用 HTML + CSS 强制覆盖 Streamlit 默认主题，特别是表格和黑色背景问题
st.markdown("""
<style>
    /* -------- 全局背景 -------- */
    .stApp {
        background-color: #FFCCCC !important;
    }

    /* -------- 顶部指标卡片 -------- */
    .hero-card {
        border-radius: 20px !important;
        padding: 30px 15px !important;
        text-align: center !important;
        box-shadow: 0 8px 20px rgba(0,0,0,0.3) !important;
        margin-bottom: 25px !important;
    }

    .card-cyan   { 
        background-color: #CCFFFF !important; 
        color: #1A1A1A !important; 
    }
    .card-blue   { 
        background-color: #99CCFF !important; 
        color: #1A1A1A !important; 
    }
    .card-yellow { 
        background-color: #FFFFCC !important; 
        color: #1A1A1A !important; 
    }

    .card-label {
        font-size: 1rem !important;
        font-weight: bold !important;
        opacity: 0.8 !important;
    }

    .card-value {
        font-size: 2.5rem !important;
        font-weight: 900 !important;
    }

    /* ========== 侧边栏整体容器 ========== */
    [data-testid="stSidebar"] {
        background-color: #F0F8FF !important;
        border-right: 2px solid #E6F0FF !important;
        box-shadow: 3px 0 10px rgba(0, 0, 0, 0.05) !important;
    }

    /* ========== 侧边栏内所有文字（标题、标签、说明文字等） ========== */
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] span {
        color: #2C3E50 !important;
        font-weight: 500 !important;
    }

    /* ========== 输入框（文本、数字、下拉框） ========== */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] select {
        background-color: white !important;
        color: #2C3E50 !important;
        border: 1px solid #FFFFCC !important;
        border-radius: 1px !important;
        padding: 8px 12px !important;
    }

    /* ========== 按钮 ========== */
    [data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(to right, #FF6666, #CCCCFF) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 6px rgba(51, 153, 255, 0.3) !important;
    }

    /* ========== Expander 标题区域（最强覆盖） ========== */
    [data-testid="stSidebar"] [data-baseweb="accordion"] {
        background-color: #E6F0FF !important;
        border-radius: 8px !important;
        border: 1px solid #B3D9FF !important;
    }

    [data-testid="stSidebar"] [data-baseweb="accordion"] > div {
        background-color: #E6F0FF !important;
        color: #1A5276 !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        font-weight: 600 !important;
        border: none !important;
    }

    [data-testid="stSidebar"] [data-baseweb="accordion"] > div:hover {
        background-color: #D1E8FF !important;
        color: #0D3D5F !important;
        transform: scale(1.02) !important;
    }


</style>

""", unsafe_allow_html=True)

# ============================
# 4. 云端数据管理 (Supabase)
# ============================
# 初始化 Supabase 连接
conn = st.connection("supabase", type=SupabaseConnection)


def get_user_data(username):
    """从云端数据库获取用户持仓"""
    try:
        # ttl="0" 确保每次都拿最新数据，不读缓存
        response = conn.query("*", table="portfolios", ttl="0").eq("username", username).execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"数据库读取失败: {e}")
        return pd.DataFrame(columns=["username", "fund_code", "fund_name", "shares", "cost"])


def update_fund_record(username, code, name, shares, cost):
    """更新或插入云端记录"""
    # 检查数据库是否已有该基金
    existing = conn.table("portfolios").select("*").eq("username", username).eq("fund_code", code).execute()

    data = {
        "username": username,
        "fund_code": code,
        "fund_name": name,
        "shares": float(shares),
        "cost": float(cost)
    }

    if len(existing.data) > 0:
        # 如果存在，则更新
        conn.table("portfolios").update(data).eq("username", username).eq("fund_code", code).execute()
    else:
        # 如果不存在，则插入
        conn.table("portfolios").insert(data).execute()


def delete_fund_record(username, code):
    """从云端删除记录"""
    conn.table("portfolios").delete().eq("username", username).eq("fund_code", code).execute()

# ============================
# 5. 基金行情抓取函数
# ============================
@st.cache_data(ttl=60)
def fetch_fund_data(code):
    """
    根据基金代码获取实时数据：
    - 昨日净值
    - 实时估值
    - 涨跌幅
    - 基金名称
    - 净值日期
    """
    code = str(code).zfill(6)  # 确保 6 位基金代码

    try:
        # 构造基金数据API URL
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        r = requests.get(url, timeout=3)

        # 接口返回的是 JS，需要截取 JSON 部分
        if "jsonpgz" in r.text:
            data = json.loads(
                r.text[r.text.find('{'):r.text.rfind('}') + 1]
            )

            return (
                float(data['dwjz']),  # 单位净值
                float(data['gsz']),  # 实时估值
                float(data['gszzl']),  # 涨跌幅 %
                data['name'],  # 基金名称
                data['jzrq'],  # 净值日期
                True
            )
    except:
        pass

    # 请求失败时的兜底返回
    return 1.0, 1.0, 0.0, "未找到", "-", False


# ============================
# 6. 侧边栏：持仓管理（双功能版）
# ============================
with st.sidebar:
    st.markdown("## 👤 账户切换")
    # 这里可以预设几个常用账号，也可以用 text_input 让用户自己输入
    user_list = ["噜噜", "咪咪"]
    with st.sidebar:
        # 这个数你可以手动输入，比如输入 5000 代表你以前赚过 5000 元
        history_profit_patch = st.number_input("🛠️ 历史盈亏修正总额", value=0.0)
    current_user = st.selectbox("选择当前查看的账户", user_list)

    st.info(f"当前正在查看: **{current_user}** 的持仓")
    st.markdown("---")


with st.sidebar:
    st.markdown("### 📝 资产管理面板")

    # --- 功能 A：原有的快捷添加（直接新增记录） ---
    with st.expander("➕ 快捷添加新持仓", expanded=False):

        # 1. 定义回调函数：专门用于更新名字
        def auto_fill_name():
            # 获取当前输入的代码
            code = st.session_state.add_code
            if code and len(code) == 6:
                # 调用你之前的抓取函数
                _, _, _, nm, _, ok = fetch_fund_data(code)
                if ok:
                    # 关键点：直接修改 session_state 中的 add_name
                    st.session_state.add_name = nm
                else:
                    st.toast(f"未找到代码 {code} 的信息", icon="⚠️")


        # 2. 基金代码输入框 (绑定 on_change)
        # 当用户输入完代码并回车（或点击别处）时，会自动触发 auto_fill_name
        in_code = st.text_input(
            "基金代码 (6位)",
            key="add_code",
            on_change=auto_fill_name,
            help="输入6位代码后按回车，自动匹配名称"
        )

        # 3. 名称输入框
        # 注意：这里去掉了 value=...，因为值完全由 session_state 管理
        f_name = st.text_input("确认名称", key="add_name")

        # 4. 其他输入框
        f_cost = st.number_input("持仓成本单价", format="%.4f", key="add_cost")
        f_share = st.number_input("持有份额", format="%.2f", key="add_share")

        # 5. 提交逻辑
        if st.button("🚀 初始入库", use_container_width=True):
            if f_name and f_share > 0:
                new_row = pd.DataFrame(
                    [[in_code.zfill(6), f_name, f_share, f_cost]],
                    columns=["基金代码", "基金名称", "持有份额", "成本单价"]
                )
                update_fund_record(current_user, in_code.zfill(6), f_name, f_share, f_cost)
                st.success(f"已存入: {f_name}")

                # 可选：清空输入框以便下一次输入
                # st.session_state.add_code = ""
                # st.session_state.add_name = ""

                time.sleep(1)  # 稍等一下让用户看到成功提示
                st.rerun()

    # --- 功能 B：买入/卖出 (升级版：三栏布局，清晰显示份额) ---
    with st.expander("🔄 存量交易管理 (买入/卖出)", expanded=True):

        # 0. 辅助函数：抓取历史净值
        def get_history_nav(code, date_str):
            try:
                ts = int(time.time() * 1000)
                # 东方财富接口
                url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=1&startDate={date_str}&endDate={date_str}&_={ts}"
                headers = {"Referer": "http://fundf10.eastmoney.com/"}
                r = requests.get(url, headers=headers, timeout=2)
                data = r.json()
                if data['Data']['LSJZList']:
                    return float(data['Data']['LSJZList'][0]['DWJZ'])
            except:
                pass
            return 0.0


        # 1. 选择基金
        current_df = pd.read_csv(PORTFOLIO_FILE, dtype={'基金代码': str})

        if not current_df.empty:
            fund_options = current_df.apply(lambda x: f"{x['基金代码']} - {x['基金名称']}", axis=1).tolist()
            trade_target = st.selectbox("选择操作基金", fund_options)
            trade_code = trade_target.split(" - ")[0]

            # 2. 交易设置 (日期与类型)
            c_date, c_type = st.columns([1.5, 1])
            with c_date:
                trade_date = st.date_input("📅 交易/净值日期", value="today")
            with c_type:
                t_type = st.radio("动作", ["买入", "卖出"], horizontal=True, label_visibility="collapsed")

            st.write("---")

            # 3. 核心数据区 (三栏布局：金额 -> 净值 -> 份额)
            # 3. 核心数据区 (2x2 布局)
            # 第一行：输入金额 和 抓取按钮
            r1_col1, r1_col2 = st.columns([1.8, 1])
            with r1_col1:
                t_amount = st.number_input("💰 交易金额 (元)", min_value=0.0, step=100.0, format="%.2f")
            with r1_col2:
                st.write(" ")  # 用于对齐垂直高度
                if st.button("🔍 抓取", use_container_width=True):
                    fetched_nav = get_history_nav(trade_code, str(trade_date))
                    if fetched_nav > 0:
                        st.session_state[f"nav_{trade_code}"] = fetched_nav
                        st.toast(f"成功获取 {trade_date} 净值: {fetched_nav}")
                    else:
                        st.toast("未查到净值，请手动输入", icon="⚠️")

            # 第二行：确认净值 和 确认份额
            r2_col1, r2_col2 = st.columns(2)
            with r2_col1:
                # 读取 session 中的净值，默认为 1.0
                default_nav = st.session_state.get(f"nav_{trade_code}", 1.0000)
                t_price = st.number_input("📉 确认净值", value=default_nav, format="%.4f", step=0.0001)

            with r2_col2:
                # 自动计算份额
                calc_share = t_amount / t_price if t_price > 0 else 0.00
                st.text_input("🍰 确认份额", value=f"{calc_share:,.2f}", disabled=True)

            # 4. 提交按钮
            if st.button("🚀 确认提交交易", use_container_width=True):
                if t_amount > 0 and t_price > 0:
                    df = get_user_data(current_user)
                    rows = df[df['基金代码'] == trade_code]
                    if rows.empty:
                        st.error("未找到该基金记录")
                        st.stop()
                    idx = rows.index[0]

                    old_share = float(df.at[idx, '持有份额'])
                    old_cost = float(df.at[idx, '成本单价'])

                    # 确保有这一列
                    if "已了结盈亏" not in df.columns: df["已了结盈亏"] = 0.0

                    if t_type == "买入":
                        new_share_part = t_amount / t_price
                        new_total_share = old_share + new_share_part
                        new_avg_cost = ((old_share * old_cost) + t_amount) / new_total_share

                        df.at[idx, '持有份额'] = new_total_share
                        df.at[idx, '成本单价'] = new_avg_cost

                        # ✅【补上的关键三行】
                        update_fund_record(current_user, trade_code, row['fund_name'], new_total_share, new_avg_cost)
                        st.success(f"加仓成功！份额 +{new_share_part:.2f}")
                        time.sleep(1)
                        st.rerun()



                    else:  # 卖出逻辑 (修改版：清仓不删行)

                        sell_share_part = t_amount / t_price

                        # 1. 检查份额够不够

                        if sell_share_part > old_share + 0.01:
                            st.error(f"份额不足！需卖出 {sell_share_part:.2f}，但你只有 {old_share:.2f}")

                            st.stop()

                        # 2. 计算剩余份额

                        remain = old_share - sell_share_part

                        # 3. 核心改动：即使卖光了(remain < 1)，也只是把份额设为 0，不要 drop 掉

                        if remain < 0.01:  # 剩下的太少就视为卖光了

                            df.at[idx, '持有份额'] = 0.0

                            st.success(f"🎉 已全额卖出变现！该基金记录已保留。")

                        else:

                            df.at[idx, '持有份额'] = remain

                            st.success(f"✅ 减仓成功！份额减少了 {sell_share_part:.2f}")

                        # 4. 保存到文件

                        df.to_csv(PORTFOLIO_FILE, index=False, encoding="utf-8-sig")

                        time.sleep(1)

                        st.rerun()
        else:
            st.info("请先添加持仓。")

# ============================
# 7. 核心收益计算逻辑（修正占比版）
# ============================
df_db = get_user_data(current_user)
view_data = []
total_v = 0;
total_d = 0;
total_h = 0

if not df_db.empty:
    temp_list = []
    # 1. 第一次循环：计算总资产
    for _, row in df_db.iterrows():
        dwjz, gsz, zf, nm, jzrq, ok = fetch_fund_data(row['基金代码'])
        share = float(row['持有份额'])
        cost = float(row['成本单价'])

        yest_val = share * dwjz
        day_inc = yest_val * (zf / 100)
        hold_inc = (gsz - cost) * share

        total_v += yest_val
        total_d += day_inc
        total_h += hold_inc

        # 先把基础数据存入临时列表
        temp_list.append({
            "代码": row['基金代码'], "基金名称": nm, "持有金额": yest_val,
            "涨幅": zf, "当日收益": day_inc, "累计收益": hold_inc, "成本": cost, "现价": gsz
        })

    # 2. 第二次循环：有了 total_v，计算精确占比
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
# 8. 初始化会话状态（用于AI聊天记录）
# ============================
# 确保AI聊天记录在页面刷新后仍然保留
if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================
# 9. 主界面逻辑（带动态 AI 侧栏）
# ============================

with st.sidebar:
    st.markdown("---")



    # 初始化 AI 显示状态
    if "show_chat" not in st.session_state:
        st.session_state.show_chat = False

    # AI 开关按钮（纯按钮，没有任何方框）
    if st.button(
        "💬 召唤 咪咪小天才" if not st.session_state.show_chat else "❌ 关闭 咪咪小天才",
        use_container_width=True
    ):
        st.session_state.show_chat = not st.session_state.show_chat
        st.rerun()

    # 清空对话历史
    if st.button("🧹 清空对话历史", use_container_width=True):
        st.session_state.messages = []
        st.rerun()



# 动态分配布局：如果开启 AI，则比例为 3:1；否则只有 1 栏
if st.session_state.show_chat:
    col_main, col_ai = st.columns([3, 1])

else:
    col_main = st.container()  # 只有主看板

# --- 左侧/主看板区域 ---
with col_main:
    st.title("📈 噜咪啦基金助手")

    # 指标卡片 - 显示总资产、当日盈亏、累计盈亏
    mc1, mc2, mc3 = st.columns(3)
    mc1.markdown(
        f'<div class="hero-card card-cyan"><div class="card-label">💰 总资产</div><div class="card-value">¥{total_v:,.2f}</div></div>',
        unsafe_allow_html=True)
    mc2.markdown(
        f'<div class="hero-card card-blue"><div class="card-label">📊 当日盈亏</div><div class="card-value">¥{total_d:+,.2f}</div></div>',
        unsafe_allow_html=True)
    # 这里的 total_h 是代码自动算的实时持仓盈亏
    # 我们直接把你的手动修正值加进去显示
    final_profit_display = total_h + history_profit_patch

    mc3.markdown(
        f'<div class="hero-card card-yellow"><div class="card-label">🏆 累计盈亏 </div><div class="card-value">¥{final_profit_display:+,.2f}</div></div>',
        unsafe_allow_html=True)

    # 持仓明细看板
    st.markdown('<div class="quant-board">', unsafe_allow_html=True)
    st.markdown("<h3>📋 持仓明细</h3>", unsafe_allow_html=True)

    # 同步行情和删除记录按钮
    ca, cb = st.columns([1, 1])
    with ca:
        if st.button("🔄 同步行情"):
            st.cache_data.clear()
            st.rerun()
    with cb:
        btn_del = st.button("🗑️ 移除记录")

    # 显示持仓数据表格
    if view_data:
        df_view = pd.DataFrame(view_data)
        # 使用data_editor显示可编辑的表格，移除滚动限制
        # ===== 动态表格高度计算 =====
        ROW_HEIGHT = 35  # 每一行高度（固定）
        HEADER_HEIGHT = 40  # 表头高度
        MAX_HEIGHT = 900  # 最大高度（防止过高）

        table_height = HEADER_HEIGHT + ROW_HEIGHT * len(df_view)
        table_height = min(table_height, MAX_HEIGHT)

        edited_df = st.data_editor(
            df_view,
            hide_index=True,
            use_container_width=True,
            column_config={
                "选": st.column_config.CheckboxColumn(width="small"),
                "持有金额": st.column_config.NumberColumn(format="¥%.2f"),
                "占比": st.column_config.ProgressColumn("持仓占比",help="该基金占总资产的比例",format="%.2f%%",min_value=0,max_value=100,),
                "涨幅": st.column_config.NumberColumn("实时涨跌",format="%+.2f%%",help="数值大于0建议关注红色趋势"),
                "当日收益": st.column_config.NumberColumn(format="¥%+.2f"),
                "累计收益": st.column_config.NumberColumn(format="¥%+.2f"),
                "收益率": st.column_config.NumberColumn(format="%+.2f%%"),
            },
            key="main_table",
            height=table_height
        )



        # 删除选中的记录
        if btn_del:
            to_del = edited_df[edited_df["选"] == True]["代码"].tolist()
            if to_del:
                for code in to_del:
                    delete_fund_record(current_user, code)
                st.rerun()
    else:
        st.info("暂无数据。")
    st.markdown('</div>', unsafe_allow_html=True)

# --- 右侧/AI 对话窗口区域 ---
if st.session_state.show_chat:
    with col_ai:
        st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)
        # 使用 CSS 稍微装饰一下这个区域，使其看起来像独立的侧边栏
        st.markdown("""
            <div style="background-color: rgba(255,255,255,0.5); padding: 6px; border-radius: 10px; border: 1px solid #E6F0FF;">
                <h3 style="color: #1A5276; margin-top:0;">🤖 聪明的咪咪</h3>
            </div>
        """, unsafe_allow_html=True)

        # 对话内容显示容器
        chat_container = st.container(height=500)


        # 显示历史聊天记录
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # 聊天输入框
        if prompt := st.chat_input("询问持仓建议..."):
            # 添加用户消息到会话状态
            st.session_state.messages.append({"role": "user", "content": prompt})

            # 显示用户消息
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

            try:
                # 初始化DeepSeek客户端
                client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

                # ... 在 AI 调用逻辑中 ...
                fund_context = f"当前用户是：{current_user}。持仓数据如下：{view_data}"
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system",
                         "content": f"你是一个专业基金助手。你正在协助 {current_user} 分析其资产。背景数据：{fund_context}"},
                        *st.session_state.messages
                    ]
                )

                # 获取AI回复
                answer = response.choices[0].message.content

                # 显示AI回复
                with chat_container:
                    with st.chat_message("assistant"):
                        st.markdown(answer)

                # 添加AI回复到会话状态
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error("AI 忙碌中...")
