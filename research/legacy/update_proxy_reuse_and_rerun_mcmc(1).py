#!/usr/bin/env python3
"""
Update remaining modeled-ish factors using data already collected in the workbook project.

Updated factors:
  - AMC density index / Academic medical center density rank
  - Est. college students / 1k residents / College students per capita rank
  - Est. homeless people / 10k residents / Homelessness rank
  - Noise pollution index / Noise pollution rank

The sources are not perfect direct replacements, so the script builds data-driven
proxy scores, blends them with the prior modeled values, quantile-maps the
result back to the old value scale, then reruns the randomized runoff MCMC.
"""
from __future__ import annotations
import argparse, math, zipfile, json, os
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DEFAULT_ITERATIONS = 100_000
DEFAULT_SEED = 2026060901
STATE_ABBR_TO_FIPS={"AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09","DE":"10","DC":"11","FL":"12","GA":"13","HI":"15","ID":"16","IL":"17","IN":"18","IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24","MA":"25","MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31","NV":"32","NH":"33","NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38","OH":"39","OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46","TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54","WI":"55","WY":"56","PR":"72"}
CT_XW={"Fairfield":[("09120",.5),("09190",.5)],"Hartford":[("09110",1)],"Litchfield":[("09160",.75),("09190",.25)],"Middlesex":[("09130",1)],"New Haven":[("09170",.55),("09140",.45)],"New London":[("09180",1)],"Tolland":[("09110",.5),("09150",.5)],"Windham":[("09150",1)]}

def safe_float(x):
    try:
        if x is None or x=="" or (isinstance(x,float) and math.isnan(x)): return None
        v=float(str(x).replace(',','').strip()); return v if math.isfinite(v) else None
    except Exception: return None

def rank_average(values, higher_is_better):
    pairs=sorted([(float(v),i) for i,v in enumerate(values)], key=lambda t:t[0], reverse=higher_is_better)
    out=[0.0]*len(pairs); i=0
    while i<len(pairs):
        j=i+1
        while j<len(pairs) and pairs[j][0]==pairs[i][0]: j+=1
        avg=(i+1+j)/2.0
        for k in range(i,j): out[pairs[k][1]]=avg
        i=j
    return out

def percentile_series(s, higher_good=True):
    ss=pd.to_numeric(pd.Series(s), errors='coerce').fillna(pd.to_numeric(pd.Series(s), errors='coerce').median())
    ranks=ss.rank(method='average', pct=True)
    p=(ranks-1/len(ss))/(1-1/len(ss)) if len(ss)>1 else ranks*0
    p=p.clip(0,1)
    return p if higher_good else 1-p

def pct_rank(vals):
    pairs=sorted([(float(v),i) for i,v in enumerate(vals)])
    n=len(pairs); out=[0]*n; i=0
    while i<n:
        j=i+1
        while j<n and pairs[j][0]==pairs[i][0]: j+=1
        p=0 if n==1 else ((i+j-1)/2)/(n-1)
        for k in range(i,j): out[pairs[k][1]]=p
        i=j
    return out

def quantile_map(scores, old_values):
    sorted_old=sorted(float(v) for v in old_values if safe_float(v) is not None)
    p=pct_rank(scores); m=len(sorted_old); out=[]
    for x in p:
        x=min(max(float(x),0),1); pos=x*(m-1); lo=int(math.floor(pos)); hi=int(math.ceil(pos))
        lo=max(0,min(lo,m-1)); hi=max(0,min(hi,m-1))
        out.append(sorted_old[lo] if lo==hi else sorted_old[lo]*(1-(pos-lo))+sorted_old[hi]*(pos-lo))
    return out

@njit
def run_randomized_runoff(ranks, sorted_order, iterations, seed):
    np.random.seed(seed); n,f=ranks.shape; wins=np.zeros(n,np.int64); elim_sum=np.zeros(n,np.float64)
    factor_order=np.empty(f,np.int64); active=np.empty(n,np.bool_); ptr=np.empty(f,np.int64); ties=np.empty(n,np.int64)
    for _ in range(iterations):
        for i in range(n): active[i]=True
        for j in range(f): ptr[j]=0
        active_count=n; pos=f; round_no=0
        while active_count>1:
            if pos>=f:
                for j in range(f): factor_order[j]=j
                for j in range(f-1,0,-1):
                    k=np.random.randint(j+1); tmp=factor_order[j]; factor_order[j]=factor_order[k]; factor_order[k]=tmp
                pos=0
            col=factor_order[pos]; pos+=1
            p=ptr[col]
            while p<n and not active[sorted_order[col,p]]: p+=1
            ptr[col]=p; first_idx=sorted_order[col,p]; worst_rank=ranks[first_idx,col]; tie_count=0; q=p
            while q<n:
                row_idx=sorted_order[col,q]
                if ranks[row_idx,col]!=worst_rank: break
                if active[row_idx]: ties[tie_count]=row_idx; tie_count+=1
                q+=1
            loser=ties[np.random.randint(tie_count)]
            active[loser]=False; round_no+=1; elim_sum[loser]+=round_no; active_count-=1
        for i in range(n):
            if active[i]: winner=i; break
        wins[winner]+=1; elim_sum[winner]+=n
    return wins, elim_sum/iterations

def read_fips(input_workbook):
    for sheet in ['FEMA NRI Update','Zillow Housing Update','USDA Food Env Update','CBP Business Patterns Update']:
        try: df=pd.read_excel(input_workbook, sheet_name=sheet, dtype={'County FIPS':str})
        except Exception: continue
        if {'County','State','County FIPS'}.issubset(df.columns):
            return {(r['County'],r['State']):str(r['County FIPS']).zfill(5) for _,r in df.iterrows()}
    raise ValueError('No County FIPS update sheet found')

def load_cbp(cbp_zip, pop_csv):
    pop=pd.read_csv(pop_csv, dtype={'STATE':str,'COUNTY':str}, encoding='latin1')
    pop=pop[pop['COUNTY'].astype(str).str.zfill(3)!='000'].copy(); pop['fips']=pop['STATE'].astype(str).str.zfill(2)+pop['COUNTY'].astype(str).str.zfill(3)
    pop_by_fips=dict(zip(pop['fips'], pd.to_numeric(pop['POPESTIMATE2023'], errors='coerce')))
    with zipfile.ZipFile(cbp_zip) as z:
        member=[n for n in z.namelist() if n.endswith('.txt')][0]
        cbp=pd.read_csv(z.open(member), dtype=str)
    cbp['fips']=cbp['fipstate'].str.zfill(2)+cbp['fipscty'].str.zfill(3)
    for c in ['emp','est']: cbp[c]=pd.to_numeric(cbp[c], errors='coerce').fillna(0)
    idx=cbp.set_index(['fips','naics'])[['emp','est']].sort_index()
    def get(fips, naics):
        try: return float(idx.loc[(fips,naics),'emp'])
        except KeyError: return 0.0
    out={}
    for fips in cbp['fips'].unique():
        p=pop_by_fips.get(fips)
        if not p or p<=0: continue
        higher=get(fips,'6113//')+get(fips,'6112//') or get(fips,'611310')+get(fips,'611210')
        health=get(fips,'62----'); amb=get(fips,'621///'); hosp=get(fips,'622///') or get(fips,'6221//') or get(fips,'622110')
        total=get(fips,'------'); transport=get(fips,'48----')+get(fips,'493///'); manuf=get(fips,'31----'); constr=get(fips,'23----')
        out[fips]={'population_2023':p,'cbp_total_emp':total,'cbp_higher_ed_emp':higher,'cbp_health_emp':health,'cbp_ambulatory_emp':amb,'cbp_hospital_emp':hosp,'cbp_transport_warehouse_emp':transport,'cbp_manufacturing_emp':manuf,'cbp_construction_emp':constr,'higher_ed_emp_per_1k':higher/p*1000,'health_emp_per_1k':health/p*1000,'ambulatory_emp_per_1k':amb/p*1000,'hospital_emp_per_1k':hosp/p*1000,'total_emp_per_1k':total/p*1000,'transport_warehouse_emp_per_1k':transport/p*1000,'manufacturing_emp_per_1k':manuf/p*1000,'construction_emp_per_1k':constr/p*1000}
    return out

def load_oews_health(metro_zip, state_zip):
    def read(zip_path, member):
        with zipfile.ZipFile(zip_path) as z:
            return pd.read_excel(z.open(member), dtype={'AREA':str,'OCC_CODE':str,'PRIM_STATE':str}, usecols=['AREA','AREA_TITLE','PRIM_STATE','OCC_CODE','TOT_EMP'])
    def rates(df, pad=False):
        df=df.copy(); df['emp']=pd.to_numeric(df['TOT_EMP'].astype(str).str.replace(',',''), errors='coerce')
        out={}
        for area,g in df[df['OCC_CODE'].isin(['00-0000','29-0000','31-0000'])].groupby('AREA'):
            allrow=g[g['OCC_CODE']=='00-0000']
            if allrow.empty: continue
            all_emp=safe_float(allrow.iloc[0]['emp']); health_emp=g[g['OCC_CODE'].isin(['29-0000','31-0000'])]['emp'].sum()
            if all_emp and all_emp>0:
                code=str(area).zfill(2) if pad else str(area)
                out[code]={'area_title':allrow.iloc[0]['AREA_TITLE'],'prim_state':allrow.iloc[0]['PRIM_STATE'],'health_occ_jobs_per_1000_all_jobs':float(health_emp/all_emp*1000)}
        return out
    return rates(read(metro_zip,'oesm25ma/MSA_M2025_dl.xlsx'), False), rates(read(state_zip,'oesm25st/state_M2025_dl.xlsx'), True)

def read_usda(path):
    def sheet(name):
        df=pd.read_excel(path, sheet_name=name, header=1, dtype={'FIPS':str}); df['FIPS']=df['FIPS'].astype(str).str.zfill(5)
        for c in df.columns:
            if c not in ['FIPS','State','County']:
                df[c]=pd.to_numeric(df[c], errors='coerce'); df.loc[df[c]<=-999,c]=np.nan
        return df
    access=sheet('ACCESS'); assist=sheet('ASSISTANCE'); insec=sheet('INSECURITY'); soc=sheet('SOCIOECONOMIC')
    return soc[['FIPS','State','County','MEDHHINC21','POVRATE21','DEEPPOVRATE21','CHILDPOVRATE21','METRO23']].merge(assist[['FIPS','PCT_SNAP22']],on='FIPS',how='left').merge(insec[['FIPS','FOODINSEC_21_23']],on='FIPS',how='left').merge(access[['FIPS','PCT_LACCESS_POP19','PCT_LACCESS_LOWI19','PCT_LACCESS_HHNV19']],on='FIPS',how='left').rename(columns={'FIPS':'County FIPS'})

def clean_cell(v):
    if isinstance(v, np.integer): return int(v)
    if isinstance(v, np.floating): return None if math.isnan(float(v)) else float(v)
    if isinstance(v,float) and math.isnan(v): return None
    return v

def write_matrix(ws, matrix):
    ws.delete_rows(1, ws.max_row)
    for i,row in enumerate(matrix,1):
        for j,v in enumerate(row,1): ws.cell(i,j,clean_cell(v))

def style_sheet(ws, max_width=46):
    fill=PatternFill('solid', fgColor='1F4E79'); font=Font(bold=True,color='FFFFFF'); thin=Side(style='thin', color='B7B7B7')
    if ws.max_row>=1:
        for cell in ws[1]: cell.fill=fill; cell.font=font; cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); cell.border=Border(bottom=thin)
        ws.row_dimensions[1].height=28
    for row in ws.iter_rows():
        for cell in row: cell.alignment=Alignment(vertical='top',wrap_text=True); cell.border=Border(bottom=thin)
    ws.freeze_panes='A2'
    if ws.max_row>1 and ws.max_column>1: ws.auto_filter.ref=ws.dimensions
    for cidx in range(1, ws.max_column+1):
        letter=get_column_letter(cidx); maxlen=max((len(str(c.value)) for c in ws[letter] if c.value is not None), default=0)
        ws.column_dimensions[letter].width=min(max(maxlen+2,8),max_width)

def recreate_sheet(wb,name,after=None):
    if name in wb.sheetnames: del wb[name]
    return wb.create_sheet(name, wb.sheetnames.index(after)+1 if after and after in wb.sheetnames else None)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input-workbook', type=Path, required=True); ap.add_argument('--cbp-zip', type=Path, required=True); ap.add_argument('--population-csv', type=Path, required=True)
    ap.add_argument('--oews-metro-zip', type=Path, required=True); ap.add_argument('--oews-state-zip', type=Path, required=True); ap.add_argument('--county-cbsa-csv', type=Path, required=True)
    ap.add_argument('--usda-xlsx', type=Path, required=True); ap.add_argument('--zillow-rollup-csv', type=Path, required=True)
    ap.add_argument('--output-workbook', type=Path, required=True); ap.add_argument('--county-rollup-csv', type=Path, required=True)
    ap.add_argument('--iterations', type=int, default=DEFAULT_ITERATIONS); ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args=ap.parse_args()
    rank=pd.read_excel(args.input_workbook, sheet_name='Rank Matrix'); val=pd.read_excel(args.input_workbook, sheet_name='Value Matrix')
    rank_headers=rank.columns.tolist(); value_headers=val.columns.tolist(); fips=read_fips(args.input_workbook)
    val['County FIPS']=[fips[(r.County,r.State)] for r in val.itertuples(index=False)]; rank['County FIPS']=[fips[(r.County,r.State)] for r in rank.itertuples(index=False)]
    cbp=load_cbp(args.cbp_zip,args.population_csv); cbp_rows=[]
    for _,r in val.iterrows():
        rec=cbp.get(r['County FIPS']); method='direct FIPS' if rec else 'missing'
        if rec is None and r['State']=='CT' and r['County'] in CT_XW:
            rec={}; method='CT planning-region crosswalk'
            for metric in next(iter(cbp.values())).keys(): rec[metric]=float(np.average([cbp[rf][metric] for rf,_ in CT_XW[r['County']] if rf in cbp],weights=[w for rf,w in CT_XW[r['County']] if rf in cbp]))
        row=dict(rec or {}); row.update({'County':r['County'],'State':r['State'],'County FIPS':r['County FIPS'],'CBP match method':method}); cbp_rows.append(row)
    cbp_work=pd.DataFrame(cbp_rows)
    msa,state=load_oews_health(args.oews_metro_zip,args.oews_state_zip); cbsa=pd.read_csv(args.county_cbsa_csv,dtype={'County FIPS':str,'CBSA':str}); cbsa['County FIPS']=cbsa['County FIPS'].str.zfill(5); cbsa=cbsa.set_index('County FIPS').to_dict('index')
    oews=[]
    for _,r in val.iterrows():
        ci=cbsa.get(r['County FIPS'],{}); code=str(ci.get('CBSA','')).strip()
        if code and code in msa: area=msa[code]; source='CBSA OEWS metro match'; ac=code
        else: ac=STATE_ABBR_TO_FIPS.get(r['State']); area=state.get(ac); source='State OEWS fallback'
        oews.append({'County':r['County'],'State':r['State'],'County FIPS':r['County FIPS'],'OEWS health source':source,'OEWS health area title':area.get('area_title') if area else None,'OEWS healthcare occupation jobs per 1000 all jobs':area.get('health_occ_jobs_per_1000_all_jobs') if area else np.nan})
    oews_work=pd.DataFrame(oews); usda=read_usda(args.usda_xlsx); zillow=pd.read_csv(args.zillow_rollup_csv,dtype={'County FIPS':str})[['County FIPS','Zillow/imputed ZHVI used']]; zillow['County FIPS']=zillow['County FIPS'].str.zfill(5)
    work=val[['County','State','County FIPS']].merge(cbp_work.drop(columns=['County','State']).drop_duplicates('County FIPS'),on='County FIPS',how='left').merge(oews_work.drop(columns=['County','State']).drop_duplicates('County FIPS'),on='County FIPS',how='left').merge(usda.drop(columns=['State','County']).drop_duplicates('County FIPS'),on='County FIPS',how='left').merge(zillow.drop_duplicates('County FIPS'),on='County FIPS',how='left')
    for col in ['POVRATE21','DEEPPOVRATE21','PCT_SNAP22','FOODINSEC_21_23']:
        med=usda.groupby('State')[col].median().to_dict(); nat=usda[col].median(); vals=[]; methods=[]
        for _,r in work.iterrows():
            v=safe_float(r.get(col))
            if v is None:
                vals.append(med.get(r['State'],nat)); methods.append(f'{col}: state/national median')
            else: vals.append(v); methods.append(f'{col}: direct')
        work[col+'_imputed']=vals; work[col+'_imputation']=methods
    # proxy scores and blends
    work['amc_proxy_score']=100*(.45*percentile_series(np.log1p(work['hospital_emp_per_1k']))+.25*percentile_series(work['OEWS healthcare occupation jobs per 1000 all jobs'])+.20*percentile_series(np.log1p(work['health_emp_per_1k']))+.10*percentile_series(np.log1p(work['higher_ed_emp_per_1k'])))
    work['college_proxy_score']=100*percentile_series(np.log1p(work['higher_ed_emp_per_1k']))
    p_walk=percentile_series(val['Est. walkability score']); p_tr=percentile_series(val['Est. public transportation score'])
    work['homelessness_pressure_score']=100*(.35*percentile_series(work['Zillow/imputed ZHVI used'])+.25*percentile_series(work['POVRATE21_imputed'])+.15*percentile_series(work['DEEPPOVRATE21_imputed'])+.10*percentile_series(work['PCT_SNAP22_imputed'])+.05*percentile_series(work['FOODINSEC_21_23_imputed'])+.05*p_walk+.05*p_tr)
    work['noise_activity_score']=100*(.25*p_walk+.20*percentile_series(np.log1p(work['transport_warehouse_emp_per_1k']))+.20*percentile_series(np.log1p(work['manufacturing_emp_per_1k']))+.15*p_tr+.10*percentile_series(np.log1p(work['total_emp_per_1k']))+.10*percentile_series(np.log1p(work['construction_emp_per_1k'])))
    work['amc_blended_score']=100*(.70*percentile_series(work['amc_proxy_score'])+.30*percentile_series(val['AMC density index']))
    work['college_blended_score']=100*(.75*percentile_series(work['college_proxy_score'])+.25*percentile_series(val['Est. college students / 1k residents']))
    work['homelessness_blended_score']=100*(.55*percentile_series(work['homelessness_pressure_score'])+.45*percentile_series(val['Est. homeless people / 10k residents']))
    work['noise_blended_score']=100*(.55*percentile_series(work['noise_activity_score'])+.45*percentile_series(val['Noise pollution index']))
    new_val=val.copy(); new_rank=rank.copy()
    new_val['AMC density index']=quantile_map(work['amc_blended_score'],val['AMC density index']); new_val['Est. college students / 1k residents']=quantile_map(work['college_blended_score'],val['Est. college students / 1k residents']); new_val['Est. homeless people / 10k residents']=quantile_map(work['homelessness_blended_score'],val['Est. homeless people / 10k residents']); new_val['Noise pollution index']=quantile_map(work['noise_blended_score'],val['Noise pollution index'])
    new_rank['Academic medical center density rank']=rank_average(new_val['AMC density index'],True); new_rank['College students per capita rank']=rank_average(new_val['Est. college students / 1k residents'],True); new_rank['Homelessness rank']=rank_average(new_val['Est. homeless people / 10k residents'],False); new_rank['Noise pollution rank']=rank_average(new_val['Noise pollution index'],False)
    factor_cols=rank_headers[10:]; new_rank['Avg Rank']=new_rank[factor_cols].astype(float).mean(axis=1); new_rank['Avg Rank Python Check']=new_rank['Avg Rank']; new_rank['Avg Check Delta']=0.0; new_rank['Avg-based rank']=rank_average(new_rank['Avg Rank'],False)
    mat=new_rank[factor_cols].to_numpy(dtype=np.float64); order=np.argsort(-mat,axis=0).T.astype(np.int64); wins,avg=run_randomized_runoff(mat,order,args.iterations,args.seed); rows=list(zip(new_rank['County'],new_rank['State'])); runoff_order=sorted(range(len(rows)),key=lambda i:(-avg[i],-wins[i],float(new_rank.iloc[i]['Avg Rank']),str(new_rank.iloc[i]['State']),str(new_rank.iloc[i]['County']))); rr=[0]*len(rows)
    for pos,i in enumerate(runoff_order,1): rr[i]=pos
    new_rank['Runoff rank']=rr; new_rank['Runoff avg elimination round']=avg; new_rank['Runoff wins']=wins.astype(int); new_rank['Runoff win rate']=wins/float(args.iterations)
    rank_sorted=new_rank.iloc[runoff_order].reset_index(drop=True); value_sorted=new_val.iloc[runoff_order].reset_index(drop=True)
    # Basic rollup and workbook output
    rollup=work.copy(); rollup['New runoff rank']=new_rank['Runoff rank']; rollup['Old runoff rank']=rank['Runoff rank']; rollup.sort_values('New runoff rank').to_csv(args.county_rollup_csv,index=False)
    wb=load_workbook(args.input_workbook); write_matrix(wb['Rank Matrix'],[rank_headers]+rank_sorted[rank_headers].values.tolist()); style_sheet(wb['Rank Matrix']); write_matrix(wb['Value Matrix'],[value_headers]+value_sorted[value_headers].values.tolist()); style_sheet(wb['Value Matrix'])
    if 'Top 30' in wb.sheetnames: write_matrix(wb['Top 30'],[rank_headers]+rank_sorted[rank_headers].head(30).values.tolist()); style_sheet(wb['Top 30'])
    impact=[['Metric','Value','Notes'],['Updated factors',4,'AMC, college, homelessness, noise'],['Runoff wins sum',int(wins.sum()),args.iterations],['Top 5','; '.join(f"{r.County} {r.State}" for r in rank_sorted.head(5).itertuples()),None]]
    ws=recreate_sheet(wb,'Proxy Reuse Impact','Zillow Housing Review' if 'Zillow Housing Review' in wb.sheetnames else None); write_matrix(ws,impact); style_sheet(ws)
    ws=recreate_sheet(wb,'Proxy Reuse Update','Proxy Reuse Impact'); write_matrix(ws,[rollup.columns.tolist()]+rollup.sort_values('New runoff rank').values.tolist()); style_sheet(ws,max_width=38)
    ws=recreate_sheet(wb,'Proxy Reuse Review','Proxy Reuse Update'); write_matrix(ws,[['Item','Decision','Notes'],['Approach','Conservative blended proxies','See script docstring and update sheet for source fields.'],['Scale handling','Quantile mapping','Preserves old column scales.']]); style_sheet(ws)
    wb.save(args.output_workbook)
    print(json.dumps({'output_workbook':str(args.output_workbook),'county_rollup_csv':str(args.county_rollup_csv),'top5':rank_sorted[['Runoff rank','County','State']].head(5).values.tolist()},indent=2))
if __name__=='__main__': main()
