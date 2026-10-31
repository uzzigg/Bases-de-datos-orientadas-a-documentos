import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import benchmark_runner

spec = importlib.util.spec_from_file_location('matriz', ROOT / 'scripts' / 'ejecutar_matriz.py')
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class BenchmarkTests(unittest.TestCase):
    def test_nearest_rank_percentiles(self):
        self.assertEqual(benchmark_runner.percentile([], .99), '')
        self.assertEqual(benchmark_runner.percentile([3, 1, 2, 4], .5), 2)
        self.assertEqual(benchmark_runner.percentile(list(range(1, 101)), .95), 95)
        self.assertEqual(benchmark_runner.percentile(list(range(1, 101)), .99), 99)

    def test_matrix_has_each_scenario_and_three_runs(self):
        runs = matrix.scenarios()
        self.assertEqual(len(runs), 162)
        cells = {}
        for item in runs:
            key = (item['engine'], item['profile'], item['query'], item['concurrency'])
            cells.setdefault(key, []).append(item['run_number'])
        self.assertEqual(len(cells), 54)
        self.assertTrue(all(sorted(values) == [1, 2, 3] for values in cells.values()))
        self.assertEqual(runs, matrix.scenarios())


if __name__ == '__main__':
    unittest.main()
