import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/codex_usage.py'
spec = importlib.util.spec_from_file_location('codex_usage', SCRIPT)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


def counts(inputs=100, cached=80, output=10):
    return {'input_tokens': inputs, 'cached_input_tokens': cached, 'output_tokens': output,
            'total_tokens': inputs + output, 'reasoning_output_tokens': 2}


def event(second, total, last=None):
    return {'timestamp': f'2026-01-01T00:00:{second:02d}Z', 'type': 'event_msg',
            'payload': {'type': 'token_count', 'info': {'total_token_usage': total, 'last_token_usage': last or total}}}


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'session.jsonl'

    def write(self, records):
        rows = [{'type': 'session_meta', 'payload': {'id': 'thread-test'}}] + records
        self.path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')

    def test_only_usage_fields_leave_the_session(self):
        private = 'DO_NOT_EXPORT_CONVERSATION'
        record = event(1, counts())
        record['payload']['info']['password'] = private
        self.write([{'type': 'event_msg', 'timestamp': '2026-01-01T00:00:00Z',
                     'payload': {'type': 'user_message', 'message': private}}, record])
        result = usage.read_usage(self.path, 'thread-test')
        self.assertNotIn(private, json.dumps(result))
        self.assertEqual(result['events'][0]['last']['input_tokens'], 100)

    def test_mismatched_session_is_rejected(self):
        self.write([event(1, counts())])
        with self.assertRaises(ValueError):
            usage.read_usage(self.path, 'other-thread')

    def test_duplicate_counters_and_partial_tail(self):
        self.write([event(1, counts()), event(2, counts())])
        with self.path.open('a') as stream:
            stream.write('{')
        result = usage.read_usage(self.path, 'thread-test')
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['duplicates'], 1)
        self.assertEqual(result['malformed_lines'], 1)

    def test_invalid_counters_are_not_claimed(self):
        for bad in [counts(100, 101), counts(-1, 0), {**counts(), 'total_tokens': 1}, {**counts(), 'input_tokens': True}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                usage.counters(bad)

    def test_following_probe_consumption_not_nearest_counter(self):
        self.write([event(2, counts()), event(4, counts(200, 160, 20), counts()),
                    event(6, counts(300, 240, 30), counts())])
        data = usage.read_usage(self.path, 'thread-test')
        probes = [{'batch': 'b', 'sequence': i, 'kind': kind,
                   'started_at': f'2026-01-01T00:00:{2*i-1:02d}Z',
                   'ended_at': f'2026-01-01T00:00:{2*i:02d}Z'}
                  for i, kind in enumerate(['full', 'compact', 'sentinel'], 1)]
        result = usage.attribute_probes(probes, data, tolerance_ms=0)
        self.assertEqual(result[0]['usage_at'], '2026-01-01T00:00:04Z')
        self.assertEqual(result[1]['usage_at'], '2026-01-01T00:00:06Z')
        self.assertEqual(result[0]['next_model_request']['uncached_input_tokens'], 20)
        result = usage.attribute_probes(probes, data, excluded=[2], tolerance_ms=0)
        self.assertEqual(result[1]['status'], 'confounded')

    def test_no_usage_is_unavailable_not_zero(self):
        self.write([])
        self.assertEqual(usage.read_usage(self.path, 'thread-test')['events'], [])


if __name__ == '__main__':
    unittest.main()
