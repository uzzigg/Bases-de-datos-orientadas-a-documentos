"""Compara resultados completos y contempla empates válidos en el Top-1000."""
import json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'Otros/consultas/agricola_detallada_01'
def read(name): return json.loads((DATA/name).read_text(encoding='utf-8'))
def dec(x): return Decimal(str(x))
def main():
    m=read('mongo_q1_disk.json'); p=read('postgres_q1_4MB.json')
    a={(x['_id']['pais'],x['_id']['cultivo']):x for x in m};b={(x['pais'],x['cultivo']):x for x in p}
    assert len(a)==len(m)==20 and set(a)==set(b)
    diffs=[]
    for key in a:
        x,y=a[key],b[key]; assert x['conteo']==y['conteo'] and dec(x['total_kg'])==dec(y['total_kg'])
        expected=dec(y['promedio_kg']); diff=abs(dec(x['promedio_kg'])-expected); tolerance=max(Decimal('0.000001'),abs(expected)*Decimal('0.000000000001'))
        assert diff<=tolerance,(key,str(diff),str(tolerance));diffs.append(diff)
    runs={name:read(name+'.json') for name in ('mongo_q2_no_disk','mongo_q2_disk','postgres_q2_4MB','postgres_q2_64MB')}
    baseline=runs['mongo_q2_no_disk']; amounts=[dec(x['total_kg']) for x in baseline]; cutoff=amounts[-1]
    assert len(amounts)==1000 and amounts==sorted(amounts,reverse=True)
    high={x['cosecha_id']:x for x in baseline if dec(x['total_kg'])>cutoff}
    reference={x['cosecha_id']:x for x in baseline}
    details={}
    for name,rows in runs.items():
        assert len(rows)==1000 and [dec(x['total_kg']) for x in rows]==amounts
        ids={x['cosecha_id']:x for x in rows}; assert len(ids)==1000
        assert {k for k,x in ids.items() if dec(x['total_kg'])>cutoff}==set(high)
        for k in ids.keys() & reference.keys():
            assert dec(ids[k]['total_kg'])==dec(reference[k]['total_kg']) and ids[k]['productor_id']==reference[k]['productor_id']
        details[name]={'filas':len(rows),'ids_comunes_con_referencia':len(ids.keys() & reference.keys())}
    out={'q1_grupos':len(a),'q1_sumas_y_conteos_exactos':True,'q1_tolerancia':'max(0.000001, abs(promedio_postgresql)*0.000000000001)',
         'q1_diferencia_maxima':str(max(diffs)),'q2_valores_y_orden_exactos':True,'q2_corte_kg':str(cutoff),
         'q2_filas_sobre_corte':len(high),'q2_variantes':details,'nota':'Empates en el corte pueden cambiar IDs; no se validó exhaustivamente el contenido de cada documento en las bases.'}
    target=ROOT/'resultados/validacion_agricola_detallada.json'
    with target.open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
