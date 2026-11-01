import csv
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from archivos_evidencia import publicar_bytes
from extraer_memoria import consultar_con_reintentos
from resguardar_matriz import recopilar
from ejecutar_matriz import scenarios
import verificar_preparacion


class RecoveryTests(unittest.TestCase):
    def test_low_disk_space_blocks_preparation_without_deleting_data(self):
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')(100,99,1)
        with patch.object(sys,'argv',['verificar_preparacion','--engine','postgres']), \
             patch('verificar_preparacion.shutil.disk_usage',return_value=usage), \
             patch('verificar_preparacion.publicar_json') as publish:
            with self.assertRaisesRegex(RuntimeError,'5 GiB'):
                verificar_preparacion.main()
            self.assertEqual(publish.call_count,1)
            self.assertTrue(publish.call_args.args[1]['issues'])

    def test_publication_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / 'evidence.json'
            publicar_bytes(target, b'original')
            with self.assertRaises(FileExistsError):
                publicar_bytes(target, b'replacement')
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(list(Path(name).glob('.evidencia-*')), [])

    def test_transient_error_retried_but_bad_request_not_retried(self):
        unavailable = urllib.error.HTTPError('http://localhost', 503, 'unavailable', None, None)
        with patch('extraer_memoria.prometheus', side_effect=[unavailable, ['series']]) as query, patch('extraer_memoria.time.sleep'):
            self.assertEqual(consultar_con_reintentos({}, 'rss', 1, 2), ['series'])
            self.assertEqual(query.call_count, 2)
        bad_request = urllib.error.HTTPError('http://localhost', 400, 'invalid', None, None)
        with patch('extraer_memoria.prometheus', side_effect=bad_request) as query, patch('extraer_memoria.time.sleep'):
            with self.assertRaises(urllib.error.HTTPError):
                consultar_con_reintentos({}, 'rss', 1, 2)
            self.assertEqual(query.call_count, 1)

    def test_snapshot_keeps_unknown_spill_error_and_detects_tampered_csv(self):
        protocol = json.loads((ROOT/'protocolo.json').read_text(encoding='utf-8'))
        case = scenarios()[0]
        run_id = f"m_prueba_{case['engine']}_{case['profile']}_{case['query']}_{case['concurrency']}_{case['run_number']}"
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root/'protocolo.json').write_text(json.dumps(protocol), encoding='utf-8')
            folder = root/'Otros'/'benchmarks'/run_id
            folder.mkdir(parents=True)
            row = dict.fromkeys(protocol['csv_columns'], '')
            row.update(engine='mongodb' if case['engine']=='mongo' else 'postgresql',
                       profile={'A':'PROFILE_A_BASELINE','B':'PROFILE_B_MEDIUM','C':'PROFILE_C_SEVERE'}[case['profile']],
                       query_id=case['query'], concurrency=case['concurrency'],run_number=case['run_number'],status='error')
            (folder/'detail.json').write_text(json.dumps({'row':row,'full_protocol':True}),encoding='utf-8')
            def write_csv(data):
                with (folder/'measurement.csv').open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=protocol['csv_columns']); writer.writeheader(); writer.writerow(data)
            write_csv(row)
            _, rows, evidence, issues = recopilar(root, 'prueba')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['status'], 'error')
            self.assertTrue(evidence[0]['spill_desconocido'])
            self.assertEqual(issues, [])
            write_csv(dict(row, status='ok'))
            _, rows, _, issues = recopilar(root, 'prueba')
            self.assertEqual(rows, [])
            self.assertEqual(len(issues), 1)


if __name__ == '__main__':
    unittest.main()
