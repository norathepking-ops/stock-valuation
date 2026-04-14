import streamlit as st
import yfinance as yf

st.set_page_config(layout="wide", page_title="Stock Valuation")

st.title("📊 Stock Valuation")

ticker_input = st.text_input("กรอก Ticker (เช่น ICHI)", value="ICHI").upper()
ticker = ticker_input + ".BK"

if st.button("ดึงข้อมูล"):
    try:
        data = yf.Ticker(ticker)
        info = data.info

        price = info.get("currentPrice", 0)
        eps = info.get("trailingEps", 0)
        pe = info.get("trailingPE", 0)

        st.metric("ราคาปัจจุบัน", f"{price:.2f} บาท")
        st.metric("EPS (TTM)", f"{eps:.2f} บาท")
        st.metric("P/E (TTM)", f"{pe:.2f}x")

    except Exception as e:
        st.error(f"ดึงข้อมูลไม่ได้: {e}")
