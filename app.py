import streamlit as st
import yfinance as yf
import json
import math

st.set_page_config(layout="wide", page_title="TFRS Equity Valuation")

# ── Helpers ──────────────────────────────────────────────────────────────────
def safe(v, default=0):
    """Return float, replacing None/NaN/inf with default."""
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default

def safe_str(v, default=""):
    return str(v) if v else default

SECTOR_MAP = {
    "Technology": "Technology",
    "Consumer Defensive": "Food & Beverage",
    "Consumer Cyclical": "Retail / Commerce",
    "Communication Services": "Telecommunications",
    "Financial Services": "Banking",
    "Healthcare": "Healthcare",
    "Energy": "Energy",
    "Basic Materials": "Materials & Construction",
    "Industrials": "Industrial",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}

def fetch_stock_data(ticker_raw: str) -> dict:
    """Fetch comprehensive data from Yahoo Finance via yfinance."""
    ticker = ticker_raw.strip().upper()
    if not ticker.endswith(".BK"):
        sym = ticker + ".BK"
    else:
        sym = ticker

    t = yf.Ticker(sym)
    info = t.info or {}

    # ── Basic info ──
    price       = safe(info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose"), 0)
    shares_raw  = safe(info.get("sharesOutstanding"), 0)
    shares_m    = shares_raw / 1e6          # millions
    mktcap_m    = safe(price * shares_m, 0)
    beta        = safe(info.get("beta"), 1.0)
    pe          = safe(info.get("trailingPE"), 0)
    pb          = safe(info.get("priceToBook"), 0)
    bvps        = safe(price / pb if pb > 0 and price > 0 else 0, 0)
    high52      = safe(info.get("fiftyTwoWeekHigh"), 0)
    low52       = safe(info.get("fiftyTwoWeekLow"), 0)
    div_yield   = safe((info.get("dividendYield") or 0) * 100, 0)
    name        = safe_str(info.get("longName") or info.get("shortName"), ticker)
    sector_raw  = safe_str(info.get("sector"), "Industrials")
    sector      = SECTOR_MAP.get(sector_raw, "Industrial")
    industry    = safe_str(info.get("industry"), sector_raw)
    base_year   = 2567  # Thai calendar current year

    # ── Financial statements ──
    IS_df = t.income_stmt      # annual, columns = period dates newest first
    BS_df = t.balance_sheet
    CF_df = t.cashflow

    def col0(df, *keys):
        """Get most recent annual value (column 0) for the first found key."""
        if df is None or df.empty:
            return 0
        for k in keys:
            if k in df.index:
                row = df.loc[k]
                v = row.iloc[0] if len(row) > 0 else 0
                return safe(v, 0)
        return 0

    # Income Statement
    rev_m     = col0(IS_df, "Total Revenue")                 / 1e6
    gross_m   = col0(IS_df, "Gross Profit")                  / 1e6
    ebitda_m  = safe(info.get("ebitda"), 0)                  / 1e6
    ebit_m    = col0(IS_df, "EBIT", "Operating Income")      / 1e6
    intexp_m  = abs(col0(IS_df, "Interest Expense"))         / 1e6
    tax_m     = abs(col0(IS_df, "Tax Provision","Income Tax Expense")) / 1e6
    pat_m     = col0(IS_df, "Net Income")                    / 1e6

    # Balance Sheet
    total_assets_m = col0(BS_df, "Total Assets")                          / 1e6
    total_liab_m   = col0(BS_df, "Total Liabilities Net Minority Interest","Total Liabilities") / 1e6
    equity_m       = col0(BS_df, "Total Equity Gross Minority Interest","Stockholders Equity","Common Stock Equity") / 1e6
    lt_debt_m      = col0(BS_df, "Long Term Debt", "Long Term Debt And Capital Lease Obligation") / 1e6
    st_debt_m      = col0(BS_df, "Current Debt","Short Long Term Debt","Short Term Borrowings") / 1e6
    cash_m         = col0(BS_df, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments") / 1e6
    ppe_m          = col0(BS_df, "Net PPE","Property Plant Equipment Net") / 1e6

    # Cash Flow
    capex_m = abs(col0(CF_df, "Capital Expenditure", "Purchase Of PPE")) / 1e6
    da_m    = abs(col0(CF_df, "Depreciation And Amortization", "Depreciation Amortization Depletion")) / 1e6

    # ── Derived ratios ──
    gm_pct  = safe(gross_m / rev_m * 100 if rev_m > 0 else 35, 35)
    sga_pct = safe((rev_m - gross_m - ebit_m - da_m) / rev_m * 100 if rev_m > 0 else 15, 15)
    sga_pct = max(0, sga_pct)
    tax_rate = safe(tax_m / (pat_m + tax_m) * 100 if (pat_m + tax_m) > 0 else 20, 20)
    tax_rate = min(max(tax_rate, 5), 35)

    # ── Working capital days (from BS/IS) ──
    ar_m  = col0(BS_df, "Receivables", "Net Receivables", "Accounts Receivable") / 1e6
    inv_m = col0(BS_df, "Inventory","Inventories") / 1e6
    ap_m  = col0(BS_df, "Accounts Payable","Payables") / 1e6
    cogs_m = rev_m - gross_m

    ar_days  = safe(ar_m / rev_m * 365 if rev_m > 0 else 45, 45)
    inv_days = safe(inv_m / cogs_m * 365 if cogs_m > 0 else 60, 60)
    ap_days  = safe(ap_m / cogs_m * 365 if cogs_m > 0 else 50, 50)

    # ── WACC defaults ──
    rf  = 2.5    # Thai 10Y bond approx
    erp = 6.0    # ERP
    sp  = 0.5    # size premium
    crp = 0.5    # country risk
    kd  = 4.5    # cost of debt estimate

    return {
        # Basic
        "name": name,
        "ticker": ticker,
        "sym": sym,
        "price": round(price, 2),
        "shares": round(shares_m, 2),
        "mktcap": round(mktcap_m, 0),
        "beta": round(beta, 2),
        "pe": round(pe, 1),
        "pb": round(pb, 2),
        "bvps": round(bvps, 2),
        "high52": round(high52, 2),
        "low52": round(low52, 2),
        "div_yield": round(div_yield, 2),
        "sector": sector,
        "industry": industry,
        "base_year": base_year,
        # IS
        "rev_m": round(rev_m, 0),
        "gross_m": round(gross_m, 0),
        "ebitda_m": round(ebitda_m, 0),
        "pat_m": round(pat_m, 0),
        "intexp_m": round(intexp_m, 0),
        "da_m": round(da_m, 0),
        "gm_pct": round(gm_pct, 1),
        "sga_pct": round(sga_pct, 1),
        "tax_rate": round(tax_rate, 1),
        # BS
        "total_assets_m": round(total_assets_m, 0),
        "total_liab_m": round(total_liab_m, 0),
        "equity_m": round(equity_m, 0),
        "lt_debt_m": round(lt_debt_m, 0),
        "st_debt_m": round(st_debt_m, 0),
        "cash_m": round(cash_m, 0),
        "ppe_m": round(ppe_m, 0),
        # CF
        "capex_m": round(capex_m, 0),
        # WC days
        "ar_days": round(ar_days, 0),
        "inv_days": round(inv_days, 0),
        "ap_days": round(ap_days, 0),
        # WACC
        "w_rf": rf,
        "w_erp": erp,
        "w_sp": sp,
        "w_crp": crp,
        "w_kd": kd,
    }


def fetch_peers_data(tickers: list[str]) -> list[dict]:
    """Fetch simplified data for peer comparison."""
    peers = []
    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            price  = safe(info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose"), 0)
            shares = safe(info.get("sharesOutstanding"), 0) / 1e6
            mktcap = safe(price * shares, 0)
            pe     = safe(info.get("trailingPE"), 0)
            pb     = safe(info.get("priceToBook"), 0)
            evebitda = safe(info.get("enterpriseToEbitda"), 0)
            roe    = safe((info.get("returnOnEquity") or 0) * 100, 0)
            npm    = safe((info.get("profitMargins") or 0) * 100, 0)
            dy     = safe((info.get("dividendYield") or 0) * 100, 0)
            peers.append({
                "ticker": sym,
                "price": round(price, 2),
                "mktcap": round(mktcap, 0),
                "pe": round(pe, 1),
                "pb": round(pb, 2),
                "evebitda": round(evebitda, 1),
                "roe": round(roe, 1),
                "npm": round(npm, 1),
                "div_yield": round(dy, 2),
            })
        except Exception:
            peers.append({"ticker": sym, "error": True})
    return peers


# ── Read HTML template ────────────────────────────────────────────────────────
with open("TFRS_Valuation_Live.html", "r", encoding="utf-8") as f:
    html_template = f.read()

# ── Patch HTML: replace proxyFetch with window.__STOCK_DATA__ receiver ────────
PATCH_JS = """
<script>
// ── Backend Bridge ──────────────────────────────────────────────────────────
// Called by Streamlit when data is ready (injected via st.components.v1.html)
window.receiveStockData = function(data) {
  if (!data || data.error) {
    setStatus('err', '⚠ ดึงข้อมูลไม่ได้: ' + (data && data.error ? data.error : 'No data'));
    setSrcChip('yahoo', 'fail');
    document.getElementById('fetch-btn').disabled = false;
    document.getElementById('fetch-icon').textContent = '⬇';
    return;
  }
  window.__STOCK_DATA__ = data;
  CURRENT_TICKER = data.ticker;

  // Populate all fields
  populateFromBackend(data);

  setStatus('ok', '✓ ' + data.name + ' (' + data.ticker + '.BK) | ราคา: ฿' + data.price.toFixed(2));
  setSrcChip('yahoo', 'ok');
  setSrcChip('finnhub', 'ok');
  document.getElementById('last-updated').textContent = 'อัปเดต: ' + new Date().toLocaleTimeString('th-TH');
  document.getElementById('fetch-btn').disabled = false;
  document.getElementById('fetch-icon').textContent = '⬇';

  setTimeout(function() { computeWACC(); calculateAll(); }, 300);
};

window.receivePeersData = function(peersArr) {
  if (!peersArr) return;
  const body = document.getElementById('peer-body');
  if (!body) return;
  // Keep subject row
  const subjectRow = body.querySelector('tr.subject-row');
  body.innerHTML = '';
  if (subjectRow) body.appendChild(subjectRow);

  let fetched = 0;
  peersArr.forEach(function(p) {
    const tr = document.createElement('tr');
    if (p.error) {
      tr.innerHTML = '<td>' + p.ticker + ' <span style="font-size:9px;color:var(--red)">(ดึงไม่ได้)</span></td>' +
        '<td colspan="10" style="color:var(--text3);font-size:10px">ข้อมูลไม่พร้อมใช้งาน</td>' +
        '<td><button class="outline-btn" onclick="this.closest(\'tr\').remove()" style="padding:3px 8px;font-size:10px">✕</button></td>';
    } else {
      const flag = p.ticker.includes('.BK') ? '🇹🇭' : p.ticker.includes('.HK') ? '🇨🇳' :
                   p.ticker.includes('.SI') ? '🇸🇬' : p.ticker.includes('.SW') ? '🇨🇭' : '🇺🇸';
      const country = p.ticker.includes('.BK') ? 'TH' : p.ticker.includes('.HK') ? 'HK' :
                      p.ticker.includes('.SI') ? 'SG' : p.ticker.includes('.SW') ? 'CH' : 'US';
      tr.innerHTML =
        '<td>' + flag + ' ' + p.ticker + '<br><span class="country-tag">' + p.ticker + '</span></td>' +
        '<td>' + flag + ' ' + country + '</td>' +
        '<td>' + (p.price > 0 ? '฿' + p.price.toFixed(2) : '—') + '</td>' +
        '<td>' + (p.mktcap > 0 ? p.mktcap.toFixed(0) : '—') + '</td>' +
        '<td class="' + (p.pe > 30 ? 'neg' : p.pe < 10 && p.pe > 0 ? 'pos' : '') + '">' + (p.pe > 0 ? p.pe.toFixed(1) + '×' : '—') + '</td>' +
        '<td>' + (p.evebitda > 0 ? p.evebitda.toFixed(1) + '×' : '—') + '</td>' +
        '<td>' + (p.pb > 0 ? p.pb.toFixed(2) + '×' : '—') + '</td>' +
        '<td class="' + (p.roe > 15 ? 'pos' : p.roe < 5 ? 'neg' : '') + '">' + (p.roe !== 0 ? p.roe.toFixed(1) + '%' : '—') + '</td>' +
        '<td class="' + (p.npm < 0 ? 'neg' : '') + '">' + (p.npm !== 0 ? p.npm.toFixed(1) + '%' : '—') + '</td>' +
        '<td>' + (p.div_yield > 0 ? p.div_yield.toFixed(2) + '%' : '—') + '</td>' +
        '<td>—</td>' +
        '<td><button class="outline-btn" onclick="this.closest(\'tr\').remove()" style="padding:3px 8px;font-size:10px">✕</button></td>';
      fetched++;
    }
    body.appendChild(tr);
  });

  document.getElementById('peers-status').innerHTML =
    '<div class="status-chip ok">✓ ดึง Peers สำเร็จ ' + fetched + '/' + peersArr.length + ' บริษัท</div>';
  setSrcChip('peers', 'ok');
};

// ── Override fetchAllData to send to Streamlit ──────────────────────────────
function fetchAllData() {
  const ticker = (document.getElementById('ticker-input').value || '').trim();
  if (!ticker) { alert('กรุณากรอก Ticker'); return; }
  CURRENT_TICKER = ticker;
  document.getElementById('a_ticker').value = ticker.toUpperCase();
  setStatus('loading', 'กำลังดึงข้อมูล...');
  document.getElementById('fetch-btn').disabled = true;
  document.getElementById('fetch-icon').innerHTML = '<div class="spinner"></div>';
  setSrcChip('yahoo', 'loading');
  setSrcChip('finnhub', 'loading');
  setSrcChip('peers', 'loading');

  // Send to Streamlit parent via postMessage
  window.parent.postMessage({ type: 'FETCH_TICKER', ticker: ticker }, '*');
}

// ── Override fetchPeers ──────────────────────────────────────────────────────
async function fetchPeers() {
  const sector = document.getElementById('a_sector').value;
  document.getElementById('peers-status').innerHTML =
    '<div class="status-chip loading"><div class="spinner"></div>กำลังดึงข้อมูล Peers...</div>';
  setSrcChip('peers', 'loading');
  window.parent.postMessage({ type: 'FETCH_PEERS', sector: sector }, '*');
}

// ── Populate from backend data object ──────────────────────────────────────
function populateFromBackend(d) {
  setLive('a_company', d.name, true);
  setLive('a_ticker', d.ticker, true);
  setLive('a_price', d.price.toFixed(2), true);
  setLive('a_shares', d.shares.toFixed(2));
  setLive('a_mktcap', d.mktcap.toFixed(0));
  setLive('a_52h', d.high52.toFixed(2));
  setLive('a_52l', d.low52.toFixed(2));
  setLive('a_beta', d.beta.toFixed(2));
  setLive('a_bvps', d.bvps.toFixed(2));
  setLive('a_pe_ttm', d.pe.toFixed(1));
  setLive('a_baseyear', d.base_year.toString());

  // Sector
  const sel = document.getElementById('a_sector');
  if (sel) sel.value = d.sector || 'Industrial';

  // Balance Sheet
  setLive('bs_cash', d.cash_m.toFixed(0));
  setLive('bs_ppe', d.ppe_m.toFixed(0));
  setLive('bs_ltdebt', d.lt_debt_m.toFixed(0));
  setLive('bs_stdebt', d.st_debt_m.toFixed(0));
  setLive('bs_equity', d.equity_m.toFixed(0));
  setLive('bs_assets', d.total_assets_m.toFixed(0));
  setLive('bs_liab', d.total_liab_m.toFixed(0));
  setLive('bs_rev_ttm', d.rev_m.toFixed(0));

  // WACC
  setLive('w_beta', d.beta.toFixed(2));
  setLive('w_mktcap', d.mktcap.toFixed(0));
  setLive('w_debt', Math.max(d.lt_debt_m + d.st_debt_m - d.cash_m, 0).toFixed(0));
  setLive('w_rf', d.w_rf.toFixed(2));
  setLive('w_erp', d.w_erp.toFixed(2));
  setLive('w_sp', d.w_sp.toFixed(2));
  setLive('w_crp', d.w_crp.toFixed(2));
  setLive('w_kd', d.w_kd.toFixed(2));

  // NAV
  setLive('nav_ppe', (d.ppe_m * 1.1).toFixed(0));
  setLive('nav_liab', d.total_liab_m.toFixed(0));

  // Year table base year
  fillYrLive('rev_0', d.rev_m.toFixed(0));
  fillYrLive('gm_0', d.gm_pct.toFixed(1));
  fillYrLive('da_0', d.da_m.toFixed(0));
  fillYrLive('capex_0', d.capex_m.toFixed(0));
  fillYrLive('intexp_0', d.intexp_m.toFixed(0));
  fillYrLive('sga_0', d.sga_pct.toFixed(1));
  fillYrLive('tax_0', d.tax_rate.toFixed(1));
  fillYrLive('ar_0', d.ar_days.toFixed(0));
  fillYrLive('inv_d_0', d.inv_days.toFixed(0));
  fillYrLive('ap_0', d.ap_days.toFixed(0));

  // Forward years (simple growth extrapolation)
  for (var i = 1; i < 6; i++) {
    var gr = i <= 2 ? 0.08 : i <= 4 ? 0.06 : 0.05;
    fillYrLive('rev_' + i, (d.rev_m * Math.pow(1 + gr, i)).toFixed(0));
    fillYrLive('da_' + i, (d.da_m * Math.pow(1.05, i)).toFixed(0));
    fillYrLive('capex_' + i, (d.capex_m * Math.pow(1.04, i)).toFixed(0));
    fillYrLive('intexp_' + i, d.intexp_m.toFixed(0));
    fillYrLive('gm_' + i, Math.min(d.gm_pct + i * 0.3, 55).toFixed(1));
    fillYrLive('sga_' + i, Math.max(d.sga_pct - i * 0.2, 8).toFixed(1));
    fillYrLive('tax_' + i, d.tax_rate.toFixed(1));
    fillYrLive('ar_' + i, Math.max(d.ar_days - i * 0.5, 30).toFixed(0));
    fillYrLive('inv_d_' + i, Math.max(d.inv_days - i * 0.5, 30).toFixed(0));
    fillYrLive('ap_' + i, d.ap_days.toFixed(0));
  }

  setSrcChip('yahoo', 'ok');
}
</script>
"""

# Inject our bridge script just before </body>
html_patched = html_template.replace("</body>", PATCH_JS + "\n</body>")

# ── Streamlit UI ──────────────────────────────────────────────────────────────
# Use session_state to persist data and communicate with iframe
if "stock_data" not in st.session_state:
    st.session_state.stock_data = None
if "peers_data" not in st.session_state:
    st.session_state.peers_data = None
if "inject_js" not in st.session_state:
    st.session_state.inject_js = ""

# ── Sidebar: receive postMessage from iframe via a hidden Streamlit listener ──
# We embed a small listener that re-posts to Streamlit via query param trick
LISTENER_HTML = """
<script>
window.addEventListener('message', function(e) {
  const d = e.data;
  if (!d || !d.type) return;
  if (d.type === 'FETCH_TICKER') {
    // Update URL to trigger Streamlit rerun
    const url = new URL(window.location.href);
    url.searchParams.set('_ticker', d.ticker);
    url.searchParams.set('_t', Date.now());
    window.location.href = url.toString();
  }
  if (d.type === 'FETCH_PEERS') {
    const url = new URL(window.location.href);
    url.searchParams.set('_sector', d.sector);
    url.searchParams.set('_t', Date.now());
    window.location.href = url.toString();
  }
});
</script>
"""

# ── Read query params ──
params = st.query_params
ticker_param = params.get("_ticker", "")
sector_param = params.get("_sector", "")

# ── Fetch logic ──
inject_call = ""

if ticker_param and ticker_param != st.session_state.get("_last_ticker", ""):
    st.session_state["_last_ticker"] = ticker_param
    with st.spinner(f"กำลังดึงข้อมูล {ticker_param}.BK จาก Yahoo Finance..."):
        try:
            data = fetch_stock_data(ticker_param)
            st.session_state.stock_data = data
            st.session_state.peers_data = None  # reset peers on new ticker
        except Exception as ex:
            st.session_state.stock_data = {"error": str(ex)}
    # Clear param so it doesn't re-run
    st.query_params.clear()

if sector_param and sector_param != st.session_state.get("_last_sector", ""):
    st.session_state["_last_sector"] = sector_param
    SECTOR_PEER_TICKERS = {
        "Technology": ["ADVANC.BK","GULF.BK","INTUCH.BK","SEA","GRAB"],
        "Food & Beverage": ["CPF.BK","TU.BK","OSP.BK","ICHI.BK","KO","NESN.SW"],
        "Industrial": ["SCC.BK","PTTGC.BK","IRPC.BK","MMM","HON"],
        "Energy": ["PTT.BK","PTTEP.BK","RATCH.BK","BP","SHEL"],
        "Banking": ["SCB.BK","KBANK.BK","BBL.BK","KTB.BK","DBS.SI"],
        "Real Estate": ["AP.BK","LH.BK","SC.BK","ORI.BK","SIRI.BK"],
        "Healthcare": ["BCH.BK","BDMS.BK","BH.BK","IHH"],
        "Retail / Commerce": ["CPALL.BK","CRC.BK","BJC.BK","MAKRO.BK","HMPRO.BK"],
        "Telecommunications": ["ADVANC.BK","DTAC.BK","TRUE.BK","INTUCH.BK"],
        "Materials & Construction": ["SCC.BK","TPIPL.BK","DCC.BK","SCCC.BK"],
        "Utilities": ["EGCO.BK","GPSC.BK","RATCH.BK","BGRIM.BK"],
        "Transportation": ["AOT.BK","BTS.BK","AAV.BK","NOK.BK"],
    }
    tickers = SECTOR_PEER_TICKERS.get(sector_param, [])
    if tickers:
        with st.spinner(f"กำลังดึงข้อมูล Peers สำหรับ {sector_param}..."):
            try:
                peers = fetch_peers_data(tickers)
                st.session_state.peers_data = peers
            except Exception as ex:
                st.session_state.peers_data = []
    st.query_params.clear()

# ── Build inject JS (called once after page loads) ──
inject_scripts = []
if st.session_state.stock_data:
    data_json = json.dumps(st.session_state.stock_data)
    inject_scripts.append(f"""
    (function waitReady(n) {{
      if (n <= 0) return;
      if (typeof window.receiveStockData === 'function') {{
        window.receiveStockData({data_json});
      }} else {{
        setTimeout(function() {{ waitReady(n-1); }}, 300);
      }}
    }})(30);
    """)
if st.session_state.peers_data is not None:
    peers_json = json.dumps(st.session_state.peers_data)
    inject_scripts.append(f"""
    (function waitPeers(n) {{
      if (n <= 0) return;
      if (typeof window.receivePeersData === 'function') {{
        window.receivePeersData({peers_json});
      }} else {{
        setTimeout(function() {{ waitPeers(n-1); }}, 300);
      }}
    }})(30);
    """)

# Inject data into HTML by appending script tag
if inject_scripts:
    inject_block = "<script>" + "\n".join(inject_scripts) + "</script>"
    html_final = html_patched.replace("</body>", inject_block + "\n</body>")
else:
    html_final = html_patched

# Render listener + app
st.components.v1.html(LISTENER_HTML, height=0)
st.components.v1.html(html_final, height=920, scrolling=True)
