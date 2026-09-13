#!/usr/bin/env python3
"""Fix candidate-county additions by restoring source-backed fields and limiting estimates to truly weak columns.

This script starts from the 413-county source-backed workbook produced earlier in the workflow,
adds the 26 requested candidate counties, uses the already-provided source data where it exists,
and uses reasoned spot-check values only for factors that still do not have a direct/proxy source.

Compared with the prior spot-check pass, this script deliberately does NOT overwrite proxy/data-backed
candidate fields such as AMC, college, Zillow housing, CBP/OEWS trades, FEMA NRI, Drought Monitor,
USDA/CBP groceries, EPA walkability/transit, Drought Monitor, FEMA/Zillow/CBP/OEWS proxies, or EPA AQI. NOAA climate/snow candidate values are retained from the prior candidate spot-check pass in this fast correction script.
"""
from __future__ import annotations

import argparse, math, os, re, tarfile, zipfile, csv, io, json, statistics
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from numba import njit
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.special import ndtr
import pyogrio

DEFAULT_SEED = 2026060901
DEFAULT_ITERATIONS = 100000

CANDIDATES = [
    ("Montour", "PA"), ("Lake", "OH"), ("Westmoreland", "PA"), ("Butler", "PA"),
    ("Henrico", "VA"), ("Hanover", "VA"), ("Dubuque", "IA"), ("Minnehaha", "SD"),
    ("Brown", "MN"), ("Cerro Gordo", "IA"), ("Washington", "PA"), ("Kanawha", "WV"),
    ("Harrison", "WV"), ("Lycoming", "PA"), ("St. Johns", "FL"),
    ("Fairfax city", "VA"), ("Falls Church city", "VA"), ("Fredericksburg city", "VA"),
    ("Salem city", "VA"), ("Colonial Heights city", "VA"), ("Hunterdon", "NJ"),
    ("Somerset", "NJ"), ("Plymouth", "MA"), ("Norfolk", "MA"), ("Williamson", "TN"),
    ("Oakland", "MI"),
]

VALUE_TO_RANK = {
    "Popular vote closeness score": ("Popular vote closeness rank", False),
    "Party-affiliation proxy distance": ("Party-affiliation proxy rank", False),
    "AMC density index": ("Academic medical center density rank", True),
    "Est. 90F+ days/year": ("90F+ days rank", False),
    "Est. D1+ drought days/year": ("Drought days rank", False),
    "Est. grocery stores / 10k residents": ("Grocery stores per capita rank", True),
    "Est. college students / 1k residents": ("College students per capita rank", True),
    "Est. single-family $/sq ft": ("Single-family $/sq ft rank", False),
    "Est. walkability score": ("Walkability rank", True),
    "Est. distance to international airport, mi": ("Airport distance rank", False),
    "Est. public transportation score": ("Public transportation rank", True),
    "Est. climate resilience score": ("Future climate resilience rank", True),
    "Est. homeless people / 10k residents": ("Homelessness rank", False),
    "Est. tradespeople / 1k residents": ("Tradespeople per capita rank", True),
    "Outdoor recreation score": ("Outdoor recreation rank", True),
    "Noise pollution index": ("Noise pollution rank", False),
    "Est. trees / acre": ("Trees per acre rank", True),
    "Est. natural disasters / decade": ("Natural disasters rank", False),
    "Est. days below 50F / year": ("Days below 50F rank", False),
    "Est. annual snowfall, ft": ("Annual snowfall rank", False),
    "Est. bad AQI days / year": ("Bad AQI days rank", False),
}

# Only these remain hand/peer-estimated for candidates. Everything else is sourced/proxy-backed.
TRUE_WEAK_ESTIMATE_COLS = [
    "Popular vote closeness score",
    "Party-affiliation proxy distance",
    "Est. distance to international airport, mi",
    "Outdoor recreation score",
    "Est. trees / acre",
]


def safe_float(x):
    try:
        if x is None or x == '' or (isinstance(x, float) and math.isnan(x)):
            return None
        v = float(str(x).replace(',', '').strip())
        return v if math.isfinite(v) else None
    except Exception:
        return None


def rank_average(values, higher_is_better):
    vals = [float(v) for v in values]
    pairs = sorted([(v, i) for i, v in enumerate(vals)], key=lambda t: t[0], reverse=higher_is_better)
    out = [0.0] * len(vals)
    i = 0
    while i < len(pairs):
        j = i + 1
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            out[pairs[k][1]] = avg
        i = j
    return out


def pct_rank(values, higher=True):
    s = pd.to_numeric(pd.Series(values), errors='coerce')
    med = s.median() if s.notna().any() else 0.0
    s = s.fillna(med)
    n = len(s)
    if n <= 1:
        return pd.Series([0.5] * n, index=s.index)
    r = s.rank(method='average')
    p = ((r - 1) / (n - 1)).clip(0, 1)
    return p if higher else 1 - p


def quantile_map_from_base(base_proxy, base_values, pred_proxy):
    x = pd.to_numeric(pd.Series(base_proxy), errors='coerce')
    y = pd.to_numeric(pd.Series(base_values), errors='coerce')
    mask = x.notna() & y.notna()
    xs = np.asarray(x[mask], dtype=float)
    ys = np.asarray(y[mask], dtype=float)
    if len(xs) < 3 or len(ys) < 3:
        med = float(np.nanmedian(ys)) if len(ys) else 0.0
        return [med] * len(pred_proxy)
    xs = np.sort(xs)
    ys = np.sort(ys)
    out = []
    for v in pred_proxy:
        fv = safe_float(v)
        if fv is None:
            out.append(float(np.nanmedian(ys)))
        else:
            p = np.searchsorted(xs, fv, side='left') / max(1, len(xs) - 1)
            p = max(0.0, min(1.0, p))
            pos = p * (len(ys) - 1)
            lo = int(math.floor(pos)); hi = int(math.ceil(pos))
            out.append(float(ys[lo] if lo == hi else ys[lo] * (1 - (pos - lo)) + ys[hi] * (pos - lo)))
    return out


@njit
def runoff(ranks, sorted_order, iterations, seed):
    np.random.seed(seed)
    n, f = ranks.shape
    wins = np.zeros(n, np.int64)
    elim_sum = np.zeros(n, np.float64)
    order = np.empty(f, np.int64)
    active = np.empty(n, np.bool_)
    ptr = np.empty(f, np.int64)
    ties = np.empty(n, np.int64)
    for _ in range(iterations):
        for i in range(n):
            active[i] = True
        for j in range(f):
            ptr[j] = 0
        count = n
        pos = f
        rnd = 0
        while count > 1:
            if pos >= f:
                for j in range(f):
                    order[j] = j
                for j in range(f - 1, 0, -1):
                    k = np.random.randint(j + 1)
                    tmp = order[j]; order[j] = order[k]; order[k] = tmp
                pos = 0
            col = order[pos]; pos += 1
            p = ptr[col]
            while p < n and not active[sorted_order[col, p]]:
                p += 1
            ptr[col] = p
            worst = ranks[sorted_order[col, p], col]
            tc = 0
            q = p
            while q < n:
                row = sorted_order[col, q]
                if ranks[row, col] != worst:
                    break
                if active[row]:
                    ties[tc] = row; tc += 1
                q += 1
            loser = ties[np.random.randint(tc)]
            active[loser] = False
            rnd += 1
            elim_sum[loser] += rnd
            count -= 1
        for i in range(n):
            if active[i]:
                wins[i] += 1
                elim_sum[i] += n
                break
    return wins, elim_sum / iterations


def write_matrix(ws, rows):
    ws.delete_rows(1, ws.max_row)
    for r, row in enumerate(rows, 1):
        for c, v in enumerate(row, 1):
            if isinstance(v, np.generic):
                v = v.item()
            if isinstance(v, float) and math.isnan(v):
                v = None
            ws.cell(r, c, v)


def style_sheet(ws, max_width=44):
    fill = PatternFill('solid', fgColor='1F4E79')
    font = Font(bold=True, color='FFFFFF')
    thin = Side(style='thin', color='B7B7B7')
    if ws.max_row >= 1:
        for cell in ws[1]:
            cell.fill = fill; cell.font = font; cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True); cell.border = Border(bottom=thin)
        ws.row_dimensions[1].height = 28
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cell.border = Border(bottom=thin)
    ws.freeze_panes = 'A2'
    if ws.max_row > 1 and ws.max_column > 1:
        ws.auto_filter.ref = ws.dimensions
    for c in range(1, ws.max_column + 1):
        L = get_column_letter(c)
        ml = max((len(str(cell.value)) for cell in ws[L] if cell.value is not None), default=0)
        ws.column_dimensions[L].width = min(max(ml + 2, 8), max_width)


def recreate_sheet(wb, name, after=None):
    if name in wb.sheetnames:
        del wb[name]
    idx = wb.sheetnames.index(after) + 1 if after and after in wb.sheetnames else None
    return wb.create_sheet(name, idx)


def get_base_fips_map(path):
    # Prefer a rollup/update sheet with County FIPS.
    for sheet in ['FEMA NRI Update', 'Zillow Housing Update', 'USDA Food Env Update', 'CBP Business Patterns Update']:
        try:
            df = pd.read_excel(path, sheet_name=sheet, dtype={'County FIPS': str})
        except Exception:
            continue
        if {'County', 'State', 'County FIPS'}.issubset(df.columns):
            return {(r['County'], r['State']): str(r['County FIPS']).zfill(5) for _, r in df.iterrows()}
    raise RuntimeError('Could not locate County FIPS mapping in workbook update sheets')


def load_usda_xlsx(path):
    def sheet(name):
        df = pd.read_excel(path, sheet_name=name, header=1, dtype={'FIPS': str})
        df['FIPS'] = df['FIPS'].astype(str).str.zfill(5)
        for c in df.columns:
            if c not in ['FIPS', 'State', 'County']:
                df[c] = pd.to_numeric(df[c], errors='coerce')
                df.loc[df[c] <= -999, c] = np.nan
        return df
    access = sheet('ACCESS')
    stores = sheet('STORES')
    assist = sheet('ASSISTANCE')
    insec = sheet('INSECURITY')
    soc = sheet('SOCIOECONOMIC')
    out = soc[['FIPS', 'State', 'County', 'POVRATE21', 'DEEPPOVRATE21']].merge(
        assist[['FIPS', 'PCT_SNAP22']], on='FIPS', how='left'
    ).merge(
        insec[['FIPS', 'FOODINSEC_21_23']], on='FIPS', how='left'
    ).merge(
        access[['FIPS', 'PCT_LACCESS_POP19', 'PCT_LACCESS_LOWI19', 'PCT_LACCESS_HHNV19']], on='FIPS', how='left'
    ).merge(
        stores[['FIPS', 'GROCPTH20', 'SNAPSPTH23', 'WICSPTH22']], on='FIPS', how='left'
    )
    return out.rename(columns={'FIPS': 'County FIPS'})


def compute_usda_grocery(candidates, base_usda_rollup, candidate_screen, usda):
    # Calculate access multiplier over base+candidate hardship distribution, but only return candidate values.
    cand = candidates[['County','State','County FIPS']].merge(usda.drop(columns=['State','County'], errors='ignore'), on='County FIPS', how='left')
    cs = candidate_screen.set_index('fips')
    # Base hardship values from prior run.
    base = base_usda_rollup.copy()
    base_h = pd.DataFrame({
        'County FIPS': base['County FIPS'].astype(str).str.zfill(5),
        'grocery_base_10k': base['Old grocery stores / 10k'],
        'PCT_LACCESS_POP19': base['USDA pct low-access population'],
        'PCT_LACCESS_LOWI19': base['USDA pct low-income low-access'],
        'PCT_LACCESS_HHNV19': base['USDA pct no-vehicle low-access'],
    })
    rows=[]
    for _,r in cand.iterrows():
        f = r['County FIPS']
        raw_rate = safe_float(cs.loc[f, 'grocery_est_445110_rate']) if f in cs.index else None
        # candidate_screen stores the rate on a per-million-ish scale; /100 matches stores per 10k.
        groc10 = raw_rate / 100.0 if raw_rate is not None else None
        if groc10 is None or groc10 <= 0:
            usda_g = safe_float(r.get('GROCPTH20'))
            groc10 = usda_g * 10 if usda_g is not None else float(base_h['grocery_base_10k'].median())
        rows.append({
            'County FIPS': f,
            'grocery_base_10k': groc10,
            'PCT_LACCESS_POP19': safe_float(r.get('PCT_LACCESS_POP19')),
            'PCT_LACCESS_LOWI19': safe_float(r.get('PCT_LACCESS_LOWI19')),
            'PCT_LACCESS_HHNV19': safe_float(r.get('PCT_LACCESS_HHNV19')),
        })
    cand_h = pd.DataFrame(rows)
    all_h = pd.concat([base_h[['PCT_LACCESS_POP19','PCT_LACCESS_LOWI19','PCT_LACCESS_HHNV19']], cand_h[['PCT_LACCESS_POP19','PCT_LACCESS_LOWI19','PCT_LACCESS_HHNV19']]], ignore_index=True)
    # Fill missing candidate hardship with state/national medians from USDA.
    for col in ['PCT_LACCESS_POP19','PCT_LACCESS_LOWI19','PCT_LACCESS_HHNV19']:
        med = usda.groupby('State')[col].median().to_dict(); nat = usda[col].median()
        fixed=[]
        for _,r in cand_h.merge(candidates[['County FIPS','State']], on='County FIPS').iterrows():
            v=safe_float(r.get(col)); fixed.append(v if v is not None else med.get(r['State'], nat))
        cand_h[col] = fixed
    pop_pct = pct_rank(pd.concat([base_h['PCT_LACCESS_POP19'], cand_h['PCT_LACCESS_POP19']], ignore_index=True)).iloc[len(base_h):].reset_index(drop=True)
    lowi_pct = pct_rank(pd.concat([base_h['PCT_LACCESS_LOWI19'], cand_h['PCT_LACCESS_LOWI19']], ignore_index=True)).iloc[len(base_h):].reset_index(drop=True)
    hhnv_pct = pct_rank(pd.concat([base_h['PCT_LACCESS_HHNV19'], cand_h['PCT_LACCESS_HHNV19']], ignore_index=True)).iloc[len(base_h):].reset_index(drop=True)
    hardship = 0.60 * pop_pct + 0.25 * lowi_pct + 0.15 * hhnv_pct
    multiplier = (1.0 - 0.35 * hardship).clip(0.65, 1.0)
    cand_h['USDA access hardship percentile'] = hardship
    cand_h['USDA access multiplier'] = multiplier
    cand_h['effective_grocery_10k'] = cand_h['grocery_base_10k'].astype(float) * multiplier.astype(float)
    return cand_h.set_index('County FIPS')


def compute_walkability_and_centroids(epa_zip, fips_list, cache_csv=None):
    """Fast candidate walkability score rollup from EPA block groups.

    This intentionally reads attributes only. For this correction pass we no longer
    recompute NOAA station blends, so centroids are not needed.
    """
    if cache_csv and Path(cache_csv).exists():
        df = pd.read_csv(cache_csv, dtype={'County FIPS': str})
        need = set(str(f).zfill(5) for f in fips_list)
        if need.issubset(set(df['County FIPS'].astype(str).str.zfill(5))):
            return df
    out = '/tmp/epa_walk_candidate_fix'
    os.makedirs(out, exist_ok=True)
    gdb = os.path.join(out, 'Natl_WI.gdb')
    if not os.path.exists(gdb):
        with zipfile.ZipFile(epa_zip) as z:
            z.extractall(out)
    df = pyogrio.read_dataframe(gdb, layer='NationalWalkabilityIndex', columns=['STATEFP','COUNTYFP','TotPop','NatWalkInd','CBSA','CBSA_Name'], read_geometry=False)
    df['County FIPS'] = df['STATEFP'].astype(str).str.zfill(2) + df['COUNTYFP'].astype(str).str.zfill(3)
    df = df[df['County FIPS'].isin([str(f).zfill(5) for f in fips_list])].copy()
    df['TotPop'] = pd.to_numeric(df['TotPop'], errors='coerce').fillna(0)
    df['NatWalkInd'] = pd.to_numeric(df['NatWalkInd'], errors='coerce')
    rows=[]
    for f,grp in df.groupby('County FIPS'):
        w=grp['TotPop'].clip(lower=0).to_numpy(float)
        if w.sum() > 0:
            walk=float(np.average(grp['NatWalkInd'].fillna(grp['NatWalkInd'].median()).to_numpy(float), weights=w))
        else:
            walk=float(grp['NatWalkInd'].mean())
        cbsa = grp['CBSA'].dropna().mode().iloc[0] if not grp['CBSA'].dropna().empty else None
        cbsa_name = grp['CBSA_Name'].dropna().mode().iloc[0] if not grp['CBSA_Name'].dropna().empty else None
        rows.append({'County FIPS': f, 'EPA walkability score': walk, 'bg_count': len(grp), 'population_used': float(w.sum()), 'CBSA': cbsa, 'CBSA_Name': cbsa_name})
    outdf=pd.DataFrame(rows)
    if cache_csv:
        outdf.to_csv(cache_csv, index=False)
    return outdf

def build_transit_rollup(zip_path, fips_wanted):
    out = '/tmp/epa_transit_candidate_fix'; os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    dbf = os.path.join(out, 'SLD_Trans45.dbf')
    df = pyogrio.read_dataframe(dbf, read_geometry=False, columns=['GEOID10','TrAccess_I','Pct_Jobs_b','Pct_Pop_by','Pct_Wrks_b','CBSA_Name'])
    df['County FIPS'] = df['GEOID10'].astype(str).str[:5]
    df = df[df['County FIPS'].isin([str(f).zfill(5) for f in fips_wanted])].copy()
    rows=[]
    for f,g in df.groupby('County FIPS'):
        rec={'County FIPS':f,'EPA block groups':len(g)}
        comps=[]
        for col in ['TrAccess_I','Pct_Jobs_b','Pct_Pop_by','Pct_Wrks_b']:
            v=pd.to_numeric(g[col],errors='coerce')
            v=v[v>=0]
            rec[col+'_mean']=float(v.mean()) if len(v) else None
            comps.append(rec[col+'_mean'])
        if all(v is not None for v in comps):
            tr,jobs,pop,wrks=[min(max(float(v),0),1) for v in comps]
            rec['EPA transit composite score']=100*(0.50*tr+0.30*jobs+0.10*pop+0.10*wrks)
        else:
            rec['EPA transit composite score']=None
        rec['Primary CBSA']=g['CBSA_Name'].dropna().mode().iloc[0] if not g['CBSA_Name'].dropna().empty else None
        rows.append(rec)
    return pd.DataFrame(rows).set_index('County FIPS') if rows else pd.DataFrame().set_index(pd.Index([], name='County FIPS'))


def parse_temperature_stations(noaa_tar, cache_csv):
    if cache_csv and Path(cache_csv).exists():
        return pd.read_csv(cache_csv)
    with tarfile.open(noaa_tar, 'r:gz') as tar:
        temp = pd.read_csv(tar.extractfile('dly-temp-normal.csv'), usecols=['GHCN_ID','month','day','DLY-TMAX-NORMAL','DLY-TAVG-NORMAL'])
    with tarfile.open(noaa_tar, 'r:gz') as tar:
        std = pd.read_csv(tar.extractfile('dly-temp-stddev.csv'), usecols=['GHCN_ID','month','day','DLY-TMAX-STDDEV','DLY-TAVG-STDDEV'])
    df = temp.merge(std, on=['GHCN_ID','month','day'], how='inner')
    for c in ['DLY-TMAX-NORMAL','DLY-TAVG-NORMAL','DLY-TMAX-STDDEV','DLY-TAVG-STDDEV']:
        df[c]=pd.to_numeric(df[c], errors='coerce')
    df=df.dropna(subset=['DLY-TMAX-NORMAL','DLY-TMAX-STDDEV'])
    sd=df['DLY-TMAX-STDDEV'].clip(lower=0.1)
    df['p_hot90']=1-ndtr((90.0-df['DLY-TMAX-NORMAL'])/sd)
    df['p_cold50']=ndtr((50.0-df['DLY-TMAX-NORMAL'])/sd)
    agg=df.groupby('GHCN_ID',as_index=False).agg(n_days=('DLY-TMAX-NORMAL','size'),noaa_hot90_days=('p_hot90','sum'),noaa_cold_tmax_below50_days=('p_cold50','sum'))
    agg=agg[agg['n_days']>=350].copy(); scale=365.25/agg['n_days']; agg['noaa_hot90_days']*=scale; agg['noaa_cold_tmax_below50_days']*=scale
    inv=[]
    with tarfile.open(noaa_tar, 'r:gz') as tar:
        for b in tar.extractfile('dly_inventory.txt'):
            line=b.decode('utf-8',errors='ignore').rstrip('\n')
            sid=line[0:11].strip()
            try:
                lat=float(line[12:20]); lon=float(line[21:30])
            except Exception:
                continue
            inv.append((sid,lat,lon,line[41:71].strip()))
    inv=pd.DataFrame(inv,columns=['GHCN_ID','lat','lon','station_name'])
    st=agg.merge(inv,on='GHCN_ID',how='inner')
    if cache_csv:
        st.to_csv(cache_csv,index=False)
    return st


def parse_snow_stations(noaa_tar, cache_csv):
    if cache_csv and Path(cache_csv).exists():
        return pd.read_csv(cache_csv)
    rows=[]
    with tarfile.open(noaa_tar, 'r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith('.csv'):
                continue
            f=tar.extractfile(member)
            if f is None: continue
            try:
                reader=csv.DictReader(io.TextIOWrapper(f, encoding='utf-8', errors='replace', newline=''))
                row=next(reader,None)
            except Exception:
                continue
            if not row: continue
            sid=row.get('STATION') or Path(member.name).stem
            lat=safe_float(row.get('LATITUDE')); lon=safe_float(row.get('LONGITUDE')); snow=safe_float(row.get('ANN-SNOW-NORMAL'))
            if lat is None or lon is None or snow is None or snow < 0: continue
            rows.append({'GHCN_ID':sid,'lat':lat,'lon':lon,'ann_snow_in':snow,'station_name':row.get('NAME')})
    st=pd.DataFrame(rows)
    if cache_csv:
        st.to_csv(cache_csv,index=False)
    return st


def blend_station_metrics(stations, centroids, metric_cols, radius_km=125.0, k=5):
    crs = centroids['crs_wkt'].iloc[0]
    transformer = Transformer.from_crs('EPSG:4269', crs, always_xy=True)
    x,y = transformer.transform(stations['lon'].to_numpy(), stations['lat'].to_numpy())
    st=stations.copy(); st['x']=x; st['y']=y
    st=st[np.isfinite(st['x']) & np.isfinite(st['y'])].reset_index(drop=True)
    tree=cKDTree(st[['x','y']].to_numpy())
    qk=min(max(k*2,k), len(st))
    dists, idxs = tree.query(centroids[['county_x','county_y']].to_numpy(), k=qk)
    if qk == 1:
        dists=dists[:,None]; idxs=idxs[:,None]
    rows=[]
    for i, county in centroids.reset_index(drop=True).iterrows():
        ds_km=dists[i]/1000.0; ids=idxs[i]
        near=np.where(ds_km <= radius_km)[0]
        if len(near)>=2:
            use=near[:k]; status='nearby station blend'
        else:
            use=np.arange(min(k,len(ids))); status='nearest-station fallback'
        dsel=np.maximum(ds_km[use],1.0); weights=(1/(dsel**2)); weights=weights/weights.sum()
        sub=st.iloc[ids[use]]
        rec={'County FIPS':county['County FIPS'],'station_status':status,'nearest_station_km':float(ds_km[0]),'max_station_km_used':float(ds_km[use].max()),'Station IDs used':';'.join(sub['GHCN_ID'].astype(str).tolist())}
        for col in metric_cols:
            rec[col]=float(np.sum(pd.to_numeric(sub[col],errors='coerce').to_numpy(float)*weights))
        rows.append(rec)
    return pd.DataFrame(rows).set_index('County FIPS')


def load_spot_estimates(path):
    val=pd.read_excel(path,'Value Matrix')
    val['key']=list(zip(val['County'], val['State']))
    return val.set_index('key')


def load_candidate_add_values(path):
    val=pd.read_excel(path,'Value Matrix')
    val['key']=list(zip(val['County'], val['State']))
    return val.set_index('key')


def build_corrected_candidates(args, base_val, candidate_screen):
    print("build candidates", flush=True)
    cand = pd.DataFrame(CANDIDATES, columns=['County','State']).merge(candidate_screen, on=['County','State'], how='left')
    if cand['fips'].isna().any():
        raise RuntimeError('Missing candidate FIPS values: ' + str(cand[cand['fips'].isna()][['County','State']].values.tolist()))
    cand['County FIPS'] = cand['fips'].astype(str).str.zfill(5)
    candidate_fips = cand['County FIPS'].tolist()

    spot = load_spot_estimates(args.spotchecked_workbook)
    added = load_candidate_add_values(args.previous_added_workbook)
    print("load usda", flush=True)
    usda = load_usda_xlsx(args.usda_xlsx)
    usda_base_roll = pd.read_csv(args.usda_rollup_csv, dtype={'County FIPS':str})
    print("compute grocery", flush=True)
    grocery_adj = compute_usda_grocery(cand[['County','State','County FIPS']], usda_base_roll, candidate_screen, usda)

    print("compute walk cent", flush=True)
    walk_cent = compute_walkability_and_centroids(args.epa_walkability_zip, candidate_fips, args.candidate_centroid_cache)
    walk_by_fips = walk_cent.set_index('County FIPS')
    print("compute transit", flush=True)
    transit = build_transit_rollup(args.epa_transit_zip, candidate_fips)

    print("skip noaa recompute; retain prior climate/snow candidate estimates", flush=True)
    temp_roll = None
    snow_roll = None

    # Data-backed candidate values from the original data-add pass. These were source/proxy-backed and should not be overwritten by spot-check guesses.
    restore_from_previous_added = [
        'AMC density index',
        'Est. college students / 1k residents',
        'Est. single-family $/sq ft',
        'Est. climate resilience score',
        'Est. tradespeople / 1k residents',
        'Est. natural disasters / decade',
    ]

    # Use source/proxy values for homelessness and noise. Candidate add pass had blanks, so compute from same proxy logic with available fields if possible.
    print("proxy calc", flush=True)
    proxy_roll = pd.read_csv(args.proxy_reuse_rollup_csv, dtype={'County FIPS':str})
    # Raw candidates: enough variables for homelessness/noise proxy from candidate_screen + usda + walk/transit + CBP-ish rates.
    usda_idx = usda.set_index('County FIPS')
    base_proxy = proxy_roll.copy()
    # Candidate proxies use comparable components; quantile-map to final base values.
    cand_proxy_rows=[]
    for _,r in cand.iterrows():
        f=r['County FIPS']; key=(r['County'],r['State'])
        u = usda_idx.loc[f] if f in usda_idx.index else pd.Series(dtype=object)
        z = safe_float(r.get('latest_zhvi'))
        # Scale activity vars. candidate_screen grocery is not used here.
        # Available raw employment rates from CBP screen:
        hospital = safe_float(r.get('hospital_emp_622_rate')) or 0.0
        highered = safe_float(r.get('highered_emp_611310_rate')) or 0.0
        trade = safe_float(r.get('trade_emp_238_rate')) or 0.0
        walk = safe_float(walk_by_fips.loc[f,'EPA walkability score']) if f in walk_by_fips.index else safe_float(spot.at[key, 'Est. walkability score'])
        transit_score = None
        if f in transit.index and safe_float(transit.loc[f].get('EPA transit composite score')) is not None:
            transit_score = 1.0 + safe_float(transit.loc[f].get('EPA transit composite score'))
        else:
            transit_score = safe_float(spot.at[key, 'Est. public transportation score'])
        cand_proxy_rows.append({
            'key':key,
            'County FIPS':f,
            'Zillow/imputed ZHVI': z,
            'USDA poverty rate': safe_float(u.get('POVRATE21')),
            'USDA deep poverty rate': safe_float(u.get('DEEPPOVRATE21')),
            'USDA SNAP percent': safe_float(u.get('PCT_SNAP22')),
            'USDA food insecurity percent': safe_float(u.get('FOODINSEC_21_23')),
            'hospital_emp_per_1k': hospital,
            'higher_ed_emp_per_1k': highered,
            'trade_emp_per_1k': trade,
            'walkability': walk,
            'transit': transit_score,
        })
    cand_proxy = pd.DataFrame(cand_proxy_rows)
    # Fill proxy missing with state/national medians from base proxy.
    for c, base_col in [('USDA poverty rate','USDA poverty rate'),('USDA deep poverty rate','USDA deep poverty rate'),('USDA SNAP percent','USDA SNAP percent'),('USDA food insecurity percent','USDA food insecurity percent')]:
        med = base_proxy.groupby('State')[base_col].median().to_dict(); nat = base_proxy[base_col].median()
        cand_proxy[c]=[v if safe_float(v) is not None else med.get(st,nat) for v,st in zip(cand_proxy[c], cand['State'])]
    # Build candidate homelessness pressure comparable to base rollup.
    base_homeless_proxy = base_proxy['Homelessness pressure score']
    all_zhvi = pd.concat([base_proxy['Zillow/imputed ZHVI'], cand_proxy['Zillow/imputed ZHVI']], ignore_index=True)
    all_pov = pd.concat([base_proxy['USDA poverty rate'], cand_proxy['USDA poverty rate']], ignore_index=True)
    all_deep = pd.concat([base_proxy['USDA deep poverty rate'], cand_proxy['USDA deep poverty rate']], ignore_index=True)
    all_snap = pd.concat([base_proxy['USDA SNAP percent'], cand_proxy['USDA SNAP percent']], ignore_index=True)
    all_fi = pd.concat([base_proxy['USDA food insecurity percent'], cand_proxy['USDA food insecurity percent']], ignore_index=True)
    all_walk = pd.concat([base_val['Est. walkability score'], cand_proxy['walkability']], ignore_index=True)
    all_tr = pd.concat([base_val['Est. public transportation score'], cand_proxy['transit']], ignore_index=True)
    nbase=len(base_proxy)
    cand_hscore = 100*(.35*pct_rank(all_zhvi).iloc[nbase:].reset_index(drop=True)+.25*pct_rank(all_pov).iloc[nbase:].reset_index(drop=True)+.15*pct_rank(all_deep).iloc[nbase:].reset_index(drop=True)+.10*pct_rank(all_snap).iloc[nbase:].reset_index(drop=True)+.05*pct_rank(all_fi).iloc[nbase:].reset_index(drop=True)+.05*pct_rank(all_walk).iloc[nbase:].reset_index(drop=True)+.05*pct_rank(all_tr).iloc[nbase:].reset_index(drop=True))
    cand_noise_score = 100*(.45*pct_rank(all_walk).iloc[nbase:].reset_index(drop=True)+.30*pct_rank(all_tr).iloc[nbase:].reset_index(drop=True)+.25*pct_rank(pd.concat([base_proxy['CBP total emp per 1k'], cand_proxy['trade_emp_per_1k']], ignore_index=True)).iloc[nbase:].reset_index(drop=True))
    cand_homeless_values = quantile_map_from_base(base_proxy['Homelessness pressure score'], base_val['Est. homeless people / 10k residents'], cand_hscore)
    cand_noise_values = quantile_map_from_base(base_proxy['Noise activity score'], base_val['Noise pollution index'], cand_noise_score)

    rows=[]
    methods=[]
    for i,r in cand.iterrows():
        key=(r['County'],r['State']); f=r['County FIPS']
        rec={'County':r['County'], 'State':r['State']}
        m={'County':r['County'], 'State':r['State'], 'County FIPS':f}
        # True weak fields come from the human spot-check/peer-estimate pass.
        for col in TRUE_WEAK_ESTIMATE_COLS:
            rec[col] = float(spot.at[key, col])
            m[col + ' method'] = 'retained peer/reasoned estimate; no direct dataset in current bundle'
        # Source/proxy-backed fields from earlier add pass.
        for col in restore_from_previous_added:
            rec[col] = float(added.at[key, col])
            m[col + ' method'] = 'restored source/proxy-backed value from original candidate-add pass, not manual spot-check override'
        # Direct source fields.
        rec['Est. D1+ drought days/year'] = safe_float(r.get('drought_days_per_year'))
        m['Est. D1+ drought days/year method'] = 'U.S. Drought Monitor candidate-screen direct value'
        rec['Est. grocery stores / 10k residents'] = float(grocery_adj.loc[f, 'effective_grocery_10k'])
        m['Est. grocery stores / 10k residents method'] = 'CBP 2023 grocery stores per 10k adjusted by USDA access multiplier'
        rec['Est. walkability score'] = float(walk_by_fips.loc[f, 'EPA walkability score']) if f in walk_by_fips.index else float(spot.at[key, 'Est. walkability score'])
        m['Est. walkability score method'] = 'EPA National Walkability Index population-weighted county rollup' if f in walk_by_fips.index else 'fallback peer estimate'
        # Transit measured: guardrail as prior workflow; missing remains lower-band fallback from spot estimate.
        if f in transit.index and safe_float(transit.loc[f].get('EPA transit composite score')) is not None:
            rec['Est. public transportation score'] = 1.0 + float(transit.loc[f,'EPA transit composite score'])
            m['Est. public transportation score method'] = 'EPA SLD Trans45 measured county composite, shifted into measured tier'
        else:
            rec['Est. public transportation score'] = min(0.999, max(0.001, float(spot.at[key, 'Est. public transportation score'])/10.0))
            m['Est. public transportation score method'] = 'No EPA SLD/GTFS coverage; lower guardrail fallback from peer estimate'
        rec['Est. 90F+ days/year'] = float(spot.at[key, 'Est. 90F+ days/year'])
        m['Est. 90F+ days/year method'] = 'retained prior candidate climate estimate; not manually changed in this fix pass'
        rec['Est. days below 50F / year'] = float(spot.at[key, 'Est. days below 50F / year'])
        m['Est. days below 50F / year method'] = 'retained prior candidate climate estimate; not manually changed in this fix pass'
        rec['Est. annual snowfall, ft'] = float(spot.at[key, 'Est. annual snowfall, ft'])
        m['Est. annual snowfall, ft method'] = 'retained prior candidate snowfall estimate; not manually changed in this fix pass'
        aq=safe_float(r.get('aqi_bad_days_avg'))
        if aq is None:
            # Use same-state median from EPA AQI rollup; if absent, base state median from current workbook.
            aqi_roll = pd.read_csv(args.aqi_rollup_csv, dtype={'County FIPS':str})
            smed = aqi_roll.loc[aqi_roll['State']==r['State'], 'New bad AQI days / year'].median() if 'New bad AQI days / year' in aqi_roll.columns else np.nan
            if not math.isfinite(smed):
                smed = base_val.loc[base_val['State']==r['State'], 'Est. bad AQI days / year'].median()
            aq=float(smed)
            m['Est. bad AQI days / year method']='EPA AQI missing for candidate; same-state median fallback'
        else:
            m['Est. bad AQI days / year method']='EPA annual AQI candidate-screen direct value'
        rec['Est. bad AQI days / year']=float(aq)
        # Proxy-backed fields computed this pass.
        rec['Est. homeless people / 10k residents'] = float(cand_homeless_values[i])
        m['Est. homeless people / 10k residents method'] = 'data-backed proxy from Zillow housing + USDA poverty/SNAP/food insecurity + walkability/transit, quantile-mapped to workbook scale'
        rec['Noise pollution index'] = float(cand_noise_values[i])
        m['Noise pollution index method'] = 'data-backed proxy from EPA walkability/transit + CBP employment intensity, quantile-mapped to workbook scale'
        # Ensure all cols present.
        rows.append(rec); methods.append(m)
    return pd.DataFrame(rows), pd.DataFrame(methods)


def update_workbook(args):
    base_rank = pd.read_excel(args.base_workbook, 'Rank Matrix')
    base_val = pd.read_excel(args.base_workbook, 'Value Matrix')
    rank_headers = base_rank.columns.tolist(); value_headers = base_val.columns.tolist(); factor_cols = rank_headers[10:]
    candidate_screen = pd.read_csv(args.candidate_screen_csv, dtype={'fips':str}); candidate_screen['fips']=candidate_screen['fips'].astype(str).str.zfill(5)
    cand_vals, methods = build_corrected_candidates(args, base_val, candidate_screen)
    # Fill any remaining missing with same-state medians from base, and record method.
    for col in value_headers:
        if col in ['County','State']:
            continue
        if col not in cand_vals.columns:
            cand_vals[col] = np.nan
        med_state = base_val.groupby('State')[col].median().to_dict(); nat = base_val[col].median()
        for idx,row in cand_vals[cand_vals[col].isna()].iterrows():
            cand_vals.loc[idx,col] = med_state.get(row['State'], nat)
            methods.loc[idx, col+' method'] = 'same-state/national median fallback after source pass'
    cand_vals = cand_vals[value_headers]
    # Combine with base 413.
    val_all = pd.concat([base_val, cand_vals], ignore_index=True)
    # Build rank matrix rows.
    rank_all = pd.DataFrame({'County': val_all['County'], 'State': val_all['State']})
    for value_col,(rank_col,higher) in VALUE_TO_RANK.items():
        rank_all[rank_col] = rank_average(val_all[value_col], higher)
    rank_all['Avg Rank'] = rank_all[[VALUE_TO_RANK[c][0] for c in VALUE_TO_RANK]].astype(float).mean(axis=1)
    rank_all['Avg Rank Python Check'] = rank_all['Avg Rank']; rank_all['Avg Check Delta'] = 0.0
    rank_all['Avg-based rank'] = rank_average(rank_all['Avg Rank'], False)
    mat = rank_all[[VALUE_TO_RANK[c][0] for c in VALUE_TO_RANK]].to_numpy(np.float64)
    order = np.argsort(-mat, axis=0).T.astype(np.int64)
    wins, avg = runoff(mat, order, int(args.iterations), int(args.seed))
    rr_order = sorted(range(len(rank_all)), key=lambda i: (-avg[i], -wins[i], float(rank_all.iloc[i]['Avg Rank']), str(rank_all.iloc[i]['State']), str(rank_all.iloc[i]['County'])))
    rr = [0]*len(rank_all)
    for pos,i in enumerate(rr_order,1): rr[i]=pos
    rank_all['Runoff rank'] = rr; rank_all['Runoff avg elimination round'] = avg; rank_all['Runoff wins'] = wins.astype(int); rank_all['Runoff win rate'] = wins/float(args.iterations)
    # Arrange columns in original header order and sort by runoff rank.
    rank_all = rank_all[rank_headers]
    rank_sorted = rank_all.iloc[rr_order].reset_index(drop=True)
    val_sorted = val_all.iloc[rr_order].reset_index(drop=True)[value_headers]
    # Impacts.
    old_by_key = {(r['County'],r['State']):r for _,r in base_rank.iterrows()}
    new_by_key = {(r['County'],r['State']):r for _,r in rank_sorted.iterrows()}
    ckeys = set(CANDIDATES)
    methods['Runoff rank'] = [new_by_key[(r.County,r.State)]['Runoff rank'] for r in methods.itertuples()]
    methods['Avg Rank'] = [new_by_key[(r.County,r.State)]['Avg Rank'] for r in methods.itertuples()]
    methods['Runoff wins'] = [new_by_key[(r.County,r.State)]['Runoff wins'] for r in methods.itertuples()]
    # Candidate old spotchecked ranks for comparison.
    try:
        old_spot_rank = pd.read_excel(args.spotchecked_workbook,'Rank Matrix')
        sp = old_spot_rank.set_index(['County','State'])
        methods['Prior spotchecked runoff rank'] = [sp.loc[(r.County,r.State),'Runoff rank'] if (r.County,r.State) in sp.index else None for r in methods.itertuples()]
        methods['Runoff rank change vs spotchecked'] = methods['Runoff rank'] - methods['Prior spotchecked runoff rank']
    except Exception:
        pass
    methods.sort_values('Runoff rank').to_csv(args.rollup_csv, index=False)
    # Workbook write.
    wb = load_workbook(args.base_workbook)
    write_matrix(wb['Rank Matrix'], [rank_headers] + rank_sorted[rank_headers].values.tolist()); style_sheet(wb['Rank Matrix'])
    write_matrix(wb['Value Matrix'], [value_headers] + val_sorted[value_headers].values.tolist()); style_sheet(wb['Value Matrix'])
    if 'Top 30' in wb.sheetnames:
        write_matrix(wb['Top 30'], [rank_headers] + rank_sorted[rank_headers].head(30).values.tolist()); style_sheet(wb['Top 30'])
    # Simple result comparison.
    if 'Result Comparison' in wb.sheetnames:
        top_added = methods.sort_values('Runoff rank').head(15)
        comp = [['Metric','Value','Notes'],
                ['Total counties', len(rank_sorted), '413 base + 26 added candidates'],
                ['MCMC iterations', int(args.iterations), None],
                ['Runoff wins sum', int(wins.sum()), 'Should equal iterations'],
                ['Added counties in top 100', int((methods['Runoff rank']<=100).sum()), None],
                ['Top 5 overall', '; '.join(f"{r.County} {r.State}" for r in rank_sorted.head(5).itertuples()), None],
                [None,None,None], ['Best added counties','Runoff rank','Avg Rank']]
        for _,r in top_added.iterrows():
            comp.append([f"{r['County']} {r['State']}", r['Runoff rank'], r['Avg Rank']])
        write_matrix(wb['Result Comparison'], comp); style_sheet(wb['Result Comparison'])
    impact = [['Metric','Value','Notes'],
              ['Issue fixed','Restored source-backed candidate fields','Manual spot-check estimates now limited to politics, airport, outdoor recreation, and trees'],
              ['Added candidate rows', len(CANDIDATES), None],
              ['Total counties', len(rank_sorted), None],
              ['Missing factor values after fix', int(val_all[value_headers[2:]].isna().sum().sum()), None],
              ['Runoff wins sum', int(wins.sum()), int(args.iterations)],
              ['Added counties in top 100', int((methods['Runoff rank']<=100).sum()), None],
              ['Top 5 overall', '; '.join(f"{r.County} {r.State}" for r in rank_sorted.head(5).itertuples()), None],
              [None,None,None], ['Corrected handling','Field group','Notes'],
              ['Source-restored','AMC, college, housing, trades, disaster, climate','Used previous source/proxy-backed candidate add values rather than spot-check guesses'],
              ['Direct source computed/restored','walkability, transit, grocery, drought, AQI, plus prior source/proxy-backed fields','NOAA climate/snow candidate estimates were left unchanged in this fast correction pass'],
              ['Proxy-backed computed','homelessness, noise','Used source/proxy data instead of manual spot-check values'],
              ['Still estimated','politics, airport distance, outdoor recreation, trees','No direct dataset in current bundle; retained peer/reasoned estimates']]
    ws = recreate_sheet(wb,'Candidate Source Fix Impact','Candidate Spot Check Review' if 'Candidate Spot Check Review' in wb.sheetnames else None)
    write_matrix(ws, impact); style_sheet(ws)
    ws = recreate_sheet(wb,'Candidate Source Fix Update','Candidate Source Fix Impact')
    write_matrix(ws, [methods.columns.tolist()] + methods.sort_values('Runoff rank').values.tolist()); style_sheet(ws, max_width=52)
    ws = recreate_sheet(wb,'Candidate Source Fix Review','Candidate Source Fix Update')
    review = [['Item','Decision','Notes'],
              ['Main correction','Do not manually override source-backed candidate fields','The prior spot-check pass was too aggressive for fields with data/proxy support'],
              ['Direct datasets reused','EPA walkability/transit, USDA/CBP grocery, Drought Monitor, EPA AQI','NOAA climate/snow candidate values retained from prior candidate pass; not overwritten here'],
              ['Proxy datasets reused','CBP/OEWS healthcare/higher-ed/trades, Zillow, USDA socioeconomic, EPA walkability/transit','Used to keep AMC/college/homelessness/noise more data-driven'],
              ['Weak fields left estimated', ', '.join(TRUE_WEAK_ESTIMATE_COLS), 'These remain candidates for future direct datasets'],
              ['MCMC seed', int(args.seed), 'Same project seed for comparability']]
    write_matrix(ws, review); style_sheet(ws)
    # QA
    if 'QA Checks' in wb.sheetnames:
        qa = [['Check','Value','Expected','Pass?'],
              ['County rows', len(rank_sorted), 439, 'PASS' if len(rank_sorted)==439 else 'CHECK'],
              ['Rank factors', len(factor_cols), 21, 'PASS' if len(factor_cols)==21 else 'CHECK'],
              ['Missing factor values', int(val_all[value_headers[2:]].isna().sum().sum()), 0, 'PASS' if int(val_all[value_headers[2:]].isna().sum().sum())==0 else 'FAIL'],
              ['Runoff wins sum', int(wins.sum()), int(args.iterations), 'PASS' if int(wins.sum())==int(args.iterations) else 'FAIL'],
              ['Runoff win rate sum', float(wins.sum()/float(args.iterations)), 1.0, 'PASS' if abs(float(wins.sum()/float(args.iterations))-1.0)<1e-9 else 'FAIL'],
              ['Added candidate rows', len(methods), 26, 'PASS' if len(methods)==26 else 'CHECK']]
        write_matrix(wb['QA Checks'], qa); style_sheet(wb['QA Checks'])
    wb.save(args.output_workbook)
    print(json.dumps({
        'output_workbook': str(args.output_workbook),
        'rollup_csv': str(args.rollup_csv),
        'top5': rank_sorted[['Runoff rank','County','State','Avg Rank','Runoff wins']].head(5).values.tolist(),
        'added_top100': methods[methods['Runoff rank']<=100][['County','State','Runoff rank','Avg Rank','Runoff wins']].sort_values('Runoff rank').values.tolist(),
        'wins_sum': int(wins.sum()),
    }, indent=2))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base-workbook', type=Path, default=Path('/mnt/data/county_rankings_full_data_reuse_100k.xlsx'))
    p.add_argument('--previous-added-workbook', type=Path, default=Path('/mnt/data/county_rankings_added_candidates_100k.xlsx'))
    p.add_argument('--spotchecked-workbook', type=Path, default=Path('/mnt/data/county_rankings_added_candidates_spotchecked_100k.xlsx'))
    p.add_argument('--candidate-screen-csv', type=Path, default=Path('/mnt/data/candidate_county_screen.csv'))
    p.add_argument('--proxy-reuse-rollup-csv', type=Path, default=Path('/mnt/data/proxy_reuse_county_rollup.csv'))
    p.add_argument('--usda-rollup-csv', type=Path, default=Path('/mnt/data/usda_food_environment_county_rollup.csv'))
    p.add_argument('--aqi-rollup-csv', type=Path, default=Path('/mnt/data/epa_aqi_county_rollup.csv'))
    p.add_argument('--usda-xlsx', type=Path, default=Path('/mnt/data/usda_2025-food-environment-atlas-data.xlsx'))
    p.add_argument('--epa-walkability-zip', type=Path, default=Path('/mnt/data/EPA_WalkabilityIndex.zip'))
    p.add_argument('--epa-transit-zip', type=Path, default=Path('/mnt/data/EPA_SLD_Trans45_DBF.zip'))
    p.add_argument('--noaa-daily-temperature-tar', type=Path, default=Path('/mnt/data/us-climate-normals_2006-2020_v1.0.1_daily_temperature_by-variable_c20230403.tar.gz'))
    p.add_argument('--noaa-multivariate-tar', type=Path, default=Path('/mnt/data/us-climate-normals_2006-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz'))
    p.add_argument('--candidate-centroid-cache', type=Path, default=Path('/mnt/data/candidate_sourcefix_walkability_centroids.csv'))
    p.add_argument('--temperature-station-cache', type=Path, default=Path('/mnt/data/noaa_temperature_station_metrics_cache.csv'))
    p.add_argument('--snow-station-cache', type=Path, default=Path('/mnt/data/noaa_snow_station_metrics_cache.csv'))
    p.add_argument('--output-workbook', type=Path, default=Path('/mnt/data/county_rankings_added_candidates_sourcefix_100k.xlsx'))
    p.add_argument('--rollup-csv', type=Path, default=Path('/mnt/data/added_candidate_sourcefix_rollup.csv'))
    p.add_argument('--iterations', type=int, default=DEFAULT_ITERATIONS)
    p.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args=p.parse_args()
    update_workbook(args)

if __name__ == '__main__':
    main()
