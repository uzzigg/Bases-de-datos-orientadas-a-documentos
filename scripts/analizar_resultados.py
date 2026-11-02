"""Audita la matriz agrícola y resume las repeticiones sin ocultar fallos."""
import collections
import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from ejecutar_matriz import scenarios

def main():
    source=ROOT/'resultados/matriz_agricola.csv'
    protocol=json.loads((ROOT/'protocolo.json').read_text(encoding='utf-8'))
    with source.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f); rows=list(reader)
        if reader.fieldnames!=protocol['csv_columns']: raise ValueError('Columnas del CSV no coinciden')
    expected={('mongodb' if c['engine']=='mongo' else 'postgresql',{'A':'PROFILE_A_BASELINE','B':'PROFILE_B_MEDIUM','C':'PROFILE_C_SEVERE'}[c['profile']],c['query'],str(c['concurrency']),str(c['run_number'])):c for c in scenarios()}
    seen=set(); groups=collections.defaultdict(list); anomalies=[]; raw=[]
    for row in rows:
        identity=tuple(row[k] for k in ('engine','profile','query_id','concurrency','run_number'))
        if identity not in expected or identity in seen: raise ValueError(f'Identidad incorrecta o duplicada: {identity}')
        seen.add(identity); c=expected[identity]
        run_id=f"m_agricola_{c['engine']}_{c['profile']}_{c['query']}_{c['concurrency']}_{c['run_number']}"
        folder=ROOT/'Otros/benchmarks'/run_id
        d=json.loads((folder/'detail.json').read_text(encoding='utf-8'))
        if any(row[k] != str(d['row'][k]) for k in protocol['csv_columns']): raise ValueError(f'CSV y evidencia difieren: {run_id}')
        if not (folder/'memory_extra.json').is_file(): anomalies.append({'run_id':run_id,'issue':'falta evidencia adicional de memoria'})
        missing=d.get('spill',{}).get('missing',0) if isinstance(d.get('spill'),dict) else 0
        item={'run_id':run_id,'status':row['status'],'latency_samples':d.get('latency_samples_fully_inside_window'),
              'successes':d.get('successful_completions_in_window'),'crossing':d.get('queries_crossing_window_end'),
              'errors':len(d.get('errors',[])),'telemetry_error':d.get('telemetry_error'),
              'profiler_missing':missing,'spill':row['disk_spill'],'cpu_usage_seconds':d.get('cpu_usage_seconds')}
        raw.append(item); groups[identity[:4]].append((row,item))
    if set(expected)!=seen: raise ValueError(f'Faltan {len(set(expected)-seen)} escenarios')
    summary=[]
    for key,entries in sorted(groups.items()):
        valid=[r for r,d in entries if r['status'] in ('ok','spill')]
        x={'engine':key[0],'profile':key[1],'query_id':key[2],'concurrency':int(key[3]),
           'n_total':len(entries),'n_valid':len(valid),'states':dict(collections.Counter(r['status'] for r,d in entries))}
        for metric in ('throughput_qps','latency_p95_ms','latency_p99_ms','cpu_throttled_seconds','max_rss_mb'):
            vals=[float(r[metric]) for r in valid if r[metric]!='']
            x[metric]={'n':len(vals),'median':statistics.median(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None}
        summary.append(x)
    result={'scope':'Análisis descriptivo agrícola; solo estados ok/spill en medianas; errores conservados',
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(rows),'cells':len(summary),
            'states':dict(collections.Counter(r['status'] for r in rows)),
            'cells_under_three_valid':sum(x['n_valid']<3 for x in summary),'anomalies':anomalies,'runs':raw,'cells_summary':summary}
    out=ROOT/'resultados/analisis_agricola.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['engine','profile','query_id','concurrency','n_total','n_valid','estados']
    for metric in ('throughput_qps','latency_p95_ms','latency_p99_ms','cpu_throttled_seconds','max_rss_mb'):
        fields.extend([metric+'_n',metric+'_mediana',metric+'_min',metric+'_max'])
    with (ROOT/'resultados/resumen_agricola.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for cell in summary:
            row={key:cell[key] for key in fields[:6]};row['estados']=json.dumps(cell['states'],ensure_ascii=False,sort_keys=True)
            for metric in ('throughput_qps','latency_p95_ms','latency_p99_ms','cpu_throttled_seconds','max_rss_mb'):
                for source_key,suffix in (('n','n'),('median','mediana'),('min','min'),('max','max')):row[metric+'_'+suffix]=cell[metric][source_key]
            writer.writerow(row)
    print(json.dumps({k:result[k] for k in ('rows','cells','states','cells_under_three_valid','anomalies')},ensure_ascii=False))

if __name__=='__main__': main()
