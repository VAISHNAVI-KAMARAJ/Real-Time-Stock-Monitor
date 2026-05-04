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
except Exception:
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
            # ✅ FIX: Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

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

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price"
    ))

    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA50"],
        mode="lines", name="SMA50",
        line=dict(width=1.5, dash='dash')
    ))

    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA200"],
        mode="lines", name="SMA200",
        line=dict(width=1.5, dash='dot')
    ))

    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        name="Volume", yaxis="y2", opacity=0.4
    ))

    fig.update_layout(
        title=f"{symbol} — Candlestick Chart",
        xaxis=dict(type="date", rangeslider=dict(visible=False)),
        yaxis=dict(title="Price"),
        yaxis2=dict(title="Volume", overlaying="y", side="right"),
        template="plotly_white",
        height=600
    )

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

# Sidebar
st.sidebar.header("Controls")
add_symbol = st.sidebar.text_input("Add stock symbol")

if st.sidebar.button("Add to watchlist"):
    sym = add_symbol.strip().upper()
    if sym and sym not in st.session_state.watchlist:
        st.session_state.watchlist.append(sym)

# Tabs
tab1, tab2, tab3 = st.tabs(["Live Monitor", "Historical Analysis", "Alerts"])

# ---------------------------
# Tab 1
# ---------------------------
with tab1:
    symbol = st.selectbox(
        "Select stock",
        st.session_state.watchlist if st.session_state.watchlist else ["AAPL"]
    )

    data = fetch_intraday(symbol, period="7d", interval="5m")

    if data.empty or "Close" not in data.columns:
        st.warning("No valid data found.")
    else:
        data = compute_indicators(data)

        try:
            # ✅ FIXED SAFE PRICE ACCESS
            latest_price = float(data["Close"].iloc[-1])
            prev_price = float(data["Close"].iloc[-2]) if len(data) >= 2 else latest_price

            change = latest_price - prev_price

            st.metric(
                label=f"{symbol} Price",
                value=f"${latest_price:.2f}",
                delta=f"{change:.2f}"
            )

        except Exception as e:
            st.error(f"Error reading price data: {e}")

        fig = plot_professional_chart(data, symbol)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Tab 2
# ---------------------------
with tab2:
    hist_symbol = st.selectbox(
        "Historical stock",
        st.session_state.watchlist if st.session_state.watchlist else ["AAPL"]
    )

    df_hist = yf.download(hist_symbol, period="1y")

    if isinstance(df_hist.columns, pd.MultiIndex):
        df_hist.columns = df_hist.columns.get_level_values(0)

    if df_hist.empty:
        st.warning("No data")
    else:
        df_hist = compute_indicators(df_hist)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_hist.index,
            open=df_hist["Open"],
            high=df_hist["High"],
            low=df_hist["Low"],
            close=df_hist["Close"]
        ))

        st.plotly_chart(fig)

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
