import streamlit as st

with open("TFRS_Valuation_Live.html", "r", encoding="utf-8") as f:
    html = f.read()

st.set_page_config(layout="wide")
st.components.v1.html(html, height=900, scrolling=True)
