"""Genera gráficas descriptivas a partir del análisis y telemetría guardados."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'resultados/graficas_agricola'
def main():
    data=json.loads((ROOT/'resultados/analisis_agricola.json').read_text(encoding='utf-8'))['cells_summary'];OUT.mkdir(parents=True,exist_ok=True)
    colors={'mongodb':'#147d4b','postgresql':'#30638e'}; styles={'PROFILE_A_BASELINE':'-','PROFILE_B_MEDIUM':'--','PROFILE_C_SEVERE':':'}
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),sharey=False)
    for ax,group in zip(axes,['Q1','Q2 bajo','Q2 alto']):
        for engine in colors:
            for profile in styles:
                q='Q1' if group=='Q1' else ('Q2_NO_DISK' if engine=='mongodb' else 'Q2_4MB') if group=='Q2 bajo' else ('Q2_DISK' if engine=='mongodb' else 'Q2_64MB')
                cells=sorted((x for x in data if x['engine']==engine and x['profile']==profile and x['query_id']==q),key=lambda x:x['concurrency'])
                vals=[x['latency_p99_ms']['median'] for x in cells]
                ax.plot([{1:0,10:1,50:2}[x['concurrency']] for x in cells],[v if v is not None and v>0 else float('nan') for v in vals],label=f"{engine} {profile[8]}",color=colors[engine],linestyle=styles[profile],marker='o')
        ax.set_title(group);ax.set_xticks([0,1,2],['1','10','50']);ax.set_yscale('log');ax.set_xlabel('Clientes');ax.grid(True,alpha=.25)
    axes[0].set_ylabel('Mediana de P99 por corrida (ms)');axes[-1].legend(fontsize=7)
    fig.suptitle('Latencia P99; celdas sin repeticiones utilizables quedan sin punto');fig.tight_layout();fig.savefig(OUT/'p99_concurrencia.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,5))
    for engine in colors:
        items=[x for x in data if x['engine']==engine and x['n_valid'] and x['throughput_qps']['median'] is not None]
        ax.scatter([x['throughput_qps']['median'] for x in items],[x['cpu_throttled_seconds']['median'] for x in items],label=engine,c=colors[engine],alpha=.7)
    ax.set_xlabel('Mediana de QPS');ax.set_ylabel('Mediana de throttling acumulado (s)');ax.set_title('Contención y rendimiento por escenario');ax.grid(True,alpha=.25);ax.legend();fig.tight_layout();fig.savefig(OUT/'throttling_qps.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.5))
    for engine in ('mongo','postgres'):
        run=f'm_agricola_{engine}_A_Q1_1_1'; path=ROOT/'Otros/benchmarks'/run/'metrics.json'; d=json.loads(path.read_text(encoding='utf-8')); vals=d['rss'][0]['values']; t0=float(vals[0][0]);ax.plot([float(x[0])-t0 for x in vals],[float(x[1])/1048576 for x in vals],label=engine,color=colors['mongodb' if engine=='mongo' else 'postgresql'])
    ax.set_xlabel('Segundos desde la primera muestra');ax.set_ylabel('RSS (MiB)');ax.set_title('RSS durante Q1, perfil A, 1 cliente, repetición 1');ax.grid(True,alpha=.25);ax.legend();fig.tight_layout();fig.savefig(OUT/'rss_ejemplo.png',dpi=170);plt.close(fig)
    print('Gráficas en',OUT)
if __name__=='__main__':main()
