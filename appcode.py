# app.py
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------
# Email configuration
# ---------------------------
try:
    SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
    SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
    SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(st.secrets.get("SMTP_PORT", 587))
except Exception as e:
    st.error("❌ Email configuration missing. Please set secrets in Streamlit Cloud.")
    st.stop()

st.set_page_config(page_title="Stock Dashboard", layout="wide")

# ---------------------------
# Session state initialization
# ---------------------------
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []
if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "alert_history" not in st.session_state:
    st.session_state.alert_history = []
if "running" not in st.session_state:
    st.session_state.running = False
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

# ---------------------------
# Utility functions
# ---------------------------
def fetch_intraday(symbol: str, period="5d", interval="1m"):
    try:
        df = yf.download(tickers=symbol, period=period, interval=interval, progress=False, threads=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.dropna(how="all")
            return df
    except Exception as e:
        st.error(f"Error fetching {symbol}: {e}")
    return pd.DataFrame()

def compute_indicators(df: pd.DataFrame):
    df = df.copy()
    if "Close" in df.columns:
        df["SMA50"] = df["Close"].rolling(window=50, min_periods=1).mean()
        df["SMA200"] = df["Close"].rolling(window=200, min_periods=1).mean()
    return df

def plot_professional_chart(df: pd.DataFrame, symbol: str):
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    candlestick = go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price"
    )
    sma50 = go.Scatter(x=df.index, y=df["SMA50"], mode="lines", name="SMA50 (short-term avg)", line=dict(width=1.5, dash='dash'))
    sma200 = go.Scatter(x=df.index, y=df["SMA200"], mode="lines", name="SMA200 (long-term avg)", line=dict(width=1.5, dash='dot'))
    volume = go.Bar(x=df.index, y=df["Volume"], name="Volume", yaxis="y2", opacity=0.4)
    
    layout = go.Layout(
        title=f"{symbol} — Candlestick Chart",
        xaxis=dict(type="date", rangeslider=dict(visible=False), title=dict(text="Date", font=dict(size=14, family="Arial", color="black"))),
        yaxis=dict(title=dict(text="Price", font=dict(size=14, family="Arial", color="black"))),
        yaxis2=dict(title=dict(text="Volume", font=dict(size=14)), overlaying="y", side="right", showgrid=False, position=1.0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        template="plotly_white",
        height=600
    )
    fig = go.Figure(data=[candlestick, sma50, sma200, volume], layout=layout)
    return fig

def send_email(recipient_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

# ---------------------------
# Layout
# ---------------------------
st.title("📊 Real-Time Stock Monitoring & Notification")
st.write("Monitor stocks, view charts, and set instant price alerts via email.")

# Sidebar controls
st.sidebar.header("Controls")
add_symbol = st.sidebar.text_input("Add stock symbol (e.g., AAPL, TCS)")
if st.sidebar.button("Add to watchlist"):
    sym = add_symbol.strip().upper()
    if sym:
        if sym not in st.session_state.watchlist:
            st.session_state.watchlist.append(sym)
            st.success(f"Added {sym} to watchlist.")
        else:
            st.info(f"{sym} already in watchlist.")

st.sidebar.markdown("---")
st.sidebar.write("Current watchlist:")
if st.session_state.watchlist:
    for s in st.session_state.watchlist:
        col1, col2 = st.sidebar.columns([4,1])
        col1.write(s)
        if col2.button("Remove", key=f"rm_{s}"):
            st.session_state.watchlist.remove(s)
            st.experimental_rerun()
else:
    st.sidebar.write("_No symbols yet._")

refresh_interval = st.sidebar.slider("Auto-refresh interval (seconds)", 5, 60, 15)
st.session_state.auto_refresh = st.sidebar.checkbox("Auto-refresh live", value=st.session_state.auto_refresh)
start_monitor = st.sidebar.button("Start Monitoring")
stop_monitor = st.sidebar.button("Stop Monitoring")

if start_monitor:
    st.session_state.running = True
if stop_monitor:
    st.session_state.running = False

st.sidebar.markdown("---")
st.sidebar.write("Export / Utilities")
if st.sidebar.button("Download Alerts History CSV"):
    if st.session_state.alert_history:
        df_hist = pd.DataFrame(st.session_state.alert_history)
        csv = df_hist.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("Download Alerts CSV", csv, file_name="alerts_history.csv")
    else:
        st.sidebar.info("No alert history yet.")

# ---------------------------
# Tabs
# ---------------------------
tab1, tab2, tab3 = st.tabs(["Live Monitor", "Historical Analysis", "Alerts"])

# ---------------------------
# Tab 1: Live Monitor
# ---------------------------
with tab1:
    st.subheader("Live Monitor")
    
    symbol_select = st.selectbox(
        "Select stock from watchlist",
        st.session_state.watchlist if st.session_state.watchlist else ["AAPL"]
    )
    symbol = symbol_select.strip().upper()

    # Fetch data
    with st.spinner(f"Fetching {symbol} data..."):
        data = fetch_intraday(symbol, period="7d", interval="5m")
        if data.empty:
            st.warning("No data found for symbol. Check symbol or try again.")
        else:
            data = compute_indicators(data)
            latest = data.iloc[-1]
            prev = data["Close"].iloc[-2] if len(data) >= 2 else latest["Close"]
            price = float(latest["Close"])
            change = price - float(prev)
            change_pct = (change / float(prev)) * 100 if float(prev) != 0 else 0
            
            col1, col2 = st.columns([2,1])
            delta_color = "normal"  # ✅ Streamlit-friendly
            col1.metric(label=f"{symbol} Price", value=f"${price:.2f}", delta=f"{change:.2f}", delta_color=delta_color)
            col2.write(f"Last refresh: {st.session_state.last_refresh or '—'}")

            # ---------------------------
            # Instant Alert Input
            # ---------------------------
            with st.expander("Set Instant Alert"):
                alert_email = st.text_input("Enter your email for alert")
                alert_price = st.number_input(f"Alert price for {symbol}", min_value=0.0, format="%.2f")
                alert_type = st.radio("Alert type", ["Price rises to target", "Price falls to target"], key=f"alert_type_{symbol}")
                
                if st.button("Set Alert", key=f"alert_{symbol}"):
                    if alert_email and alert_price > 0:
                        alert_record = {
                            "id": len(st.session_state.alerts)+1,
                            "symbol": symbol,
                            "target_price": alert_price,
                            "alert_type": alert_type,
                            "recipient_email": alert_email,
                            "triggered": False,
                            "created_at": datetime.utcnow().isoformat()
                        }
                        st.session_state.alerts.append(alert_record)
                        st.success(f"Alert set for {symbol} at ${alert_price:.2f} ({alert_type}) to {alert_email}")
                    else:
                        st.warning("Enter valid email and price.")

            # Chart
            fig = plot_professional_chart(data, symbol)
            st.plotly_chart(fig, use_container_width=True)
            
            st.info("""
            **Chart explanation:**  
            - Candlesticks: open/high/low/close  
            - SMA50 (dashed line): average of last 50 intervals (short-term trend)  
            - SMA200 (dotted line): average of last 200 intervals (long-term trend)  
            - Volume bars (right axis): trading activity  
            """)

# ---------------------------
# Tab 2: Historical Analysis
# ---------------------------
with tab2:
    st.subheader("Historical Analysis")
    
    default_symbol = "AAPL"
    hist_symbol = st.selectbox(
        "Select stock for historical charts",
        st.session_state.watchlist if st.session_state.watchlist else [default_symbol]
    ).strip().upper()
    
    days = st.slider("Days of history", 30, 3650, 365)
    interval = st.selectbox("Interval", ["1d", "1wk", "1mo"])
    
    with st.spinner("Fetching historical data..."):
        df_hist = yf.download(tickers=hist_symbol, period=f"{days}d", interval=interval, progress=False)
        if df_hist is None or df_hist.empty:
            st.warning("No historical data found.")
        else:
            df_hist = compute_indicators(df_hist)
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Candlestick(
                x=df_hist.index, open=df_hist["Open"], high=df_hist["High"],
                low=df_hist["Low"], close=df_hist["Close"], name="Price"))
            fig_hist.add_trace(go.Scatter(x=df_hist.index, y=df_hist["SMA50"], name="SMA50 (short-term)", line=dict(dash="dash")))
            fig_hist.add_trace(go.Scatter(x=df_hist.index, y=df_hist["SMA200"], name="SMA200 (long-term)", line=dict(dash="dot")))
            fig_hist.update_layout(title=f"{hist_symbol} Historical ({interval})", template="plotly_white", height=700)
            st.plotly_chart(fig_hist, use_container_width=True)
            st.dataframe(df_hist.tail(50))

# ---------------------------
# Tab 3: Alerts
# ---------------------------
with tab3:
    st.subheader("Alerts Manager")
    if st.session_state.alerts:
        df_alerts = pd.DataFrame(st.session_state.alerts)
        st.dataframe(df_alerts[["id","symbol","target_price","alert_type","recipient_email","triggered","created_at"]])
        c1, c2, c3 = st.columns(3)
        if c1.button("Remove all alerts"):
            st.session_state.alerts = []
            st.success("All alerts removed.")
        if c2.button("Clear alert history"):
            st.session_state.alert_history = []
            st.success("Alert history cleared.")
        if c3.button("Download alerts CSV"):
            csv = df_alerts.to_csv(index=False).encode("utf-8")
            st.download_button("Download", csv, file_name="alerts.csv")
    else:
        st.write("_No active alerts_")
    
    st.markdown("---")
    st.write("Triggered alert history:")
    if st.session_state.alert_history:
        df_hist = pd.DataFrame(st.session_state.alert_history)
        st.dataframe(df_hist)
    else:
        st.write("_No alerts have triggered yet._")

# ---------------------------
# Monitoring loop
# ---------------------------
def check_alerts_and_notify():
    for alert in st.session_state.alerts:
        if alert.get("triggered"): 
            continue
        symbol = alert["symbol"]
        latest_df = fetch_intraday(symbol, period="2d", interval="5m")
        if latest_df.empty:
            continue
        latest_price = float(latest_df["Close"].iloc[-1])
        trigger = False
        
        if alert["alert_type"] == "Price rises to target" and latest_price >= float(alert["target_price"]):
            trigger = True
        elif alert["alert_type"] == "Price falls to target" and latest_price <= float(alert["target_price"]):
            trigger = True
        
        if trigger:
            alert["triggered"] = True
            alert["triggered_at"] = datetime.utcnow().isoformat()
            record = {
                "id": alert["id"],
                "symbol": symbol,
                "target_price": alert["target_price"],
                "actual_price": latest_price,
                "alert_type": alert["alert_type"],
                "recipient_email": alert["recipient_email"],
                "triggered_at": alert["triggered_at"]
            }
            st.session_state.alert_history.append(record)
            st.toast(f"ALERT: {symbol} {alert['alert_type']} — Current ${latest_price:.2f}")
            
            # Email
            subject = f"Stock Alert: {symbol} {alert['alert_type']}"
            body = f"Your alert for {symbol} was triggered.\nTarget: ${alert['target_price']:.2f}\nCurrent: ${latest_price:.2f}\nTime (UTC): {alert['triggered_at']}"
            success, err = send_email(alert["recipient_email"], subject, body)
            if success: st.success(f"Email sent to {alert['recipient_email']}")
            else: st.error(f"Failed sending email: {err}")

if st.session_state.running:
    check_alerts_and_notify()
    st.session_state.last_refresh = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    if st.session_state.auto_refresh:
        time.sleep(refresh_interval)
        st.experimental_rerun()
else:
    st.write("Monitoring stopped. Click **Start Monitoring** in sidebar to run alerts.")
