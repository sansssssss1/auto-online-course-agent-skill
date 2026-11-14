import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'inspect_tasks.py'
spec = importlib.util.spec_from_file_location('inspect_tasks', SCRIPT)
tasks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tasks)


def snapshot(items, confirmed=True):
    return {'schema_version': 1, 'platform': 'chaoxing',
            'scope': {'account_alias': 'a', 'course_key': 'c', 'view': 'homework'},
            'captured_at': '2026-01-01T00:00:00+08:00', 'authoritative': confirmed, 'items': items}


def item(key='one', status='pending', deadline='page text'):
    return {'id': key, 'title': 'Example task', 'kind': 'homework', 'status': status, 'deadline': deadline}


class TaskToolsTests(unittest.TestCase):
    def test_summary_does_not_claim_completion(self):
        result = tasks.summary(snapshot([item(status='completed')]))
        self.assertEqual(result['counts'], {'completed': 1})
        self.assertEqual(result['completion_claim'], 'not-established-by-list-tool')

    def test_empty_unconfirmed_is_not_complete(self):
        result = tasks.summary(snapshot([], False))
        self.assertFalse(result['loaded_range_confirmed'])
        self.assertTrue(result['warnings'])

    def test_compare_added_changed_and_unobserved(self):
        before = snapshot([item(), item('old')])
        after = snapshot([item(status='submitted'), item('new')])
        result = tasks.compare(before, after)
        self.assertEqual([x['id'] for x in result['added']], ['new'])
        self.assertEqual([x['id'] for x in result['not_observed_now']], ['old'])
        self.assertEqual(result['changed'][0]['changes']['status']['after'], 'submitted')
        self.assertEqual(result['automatic_actions'], [])

    def test_different_scope_rejected(self):
        for key in ('account_alias', 'course_key', 'view'):
            other = snapshot([])
            other['scope'][key] = 'other'
            with self.assertRaises(ValueError):
                tasks.compare(snapshot([]), other)

    def test_different_platform_rejected(self):
        other = snapshot([])
        other['platform'] = 'icourse163'
        with self.assertRaises(ValueError):
            tasks.compare(snapshot([]), other)

    def test_partial_list_is_not_removal(self):
        result = tasks.compare(snapshot([item()]), snapshot([], False))
        self.assertFalse(result['range_confirmed'])
        self.assertTrue(result['warnings'])

    def test_metadata_timestamp_and_row_order_are_not_task_changes(self):
        before, after = snapshot([item(), item('two')]), snapshot([item('two'), item()])
        after['captured_at'] = 'later'
        after['items'][0]['row_index'] = 8
        self.assertEqual(tasks.compare(before, after)['changed'], [])

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'snapshot.json'
            source.write_text(json.dumps(snapshot([item(), item()])), encoding='utf-8')
            with self.assertRaises(ValueError):
                tasks.load_snapshot(source)

    def test_bad_scope_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'snapshot.json'
            data = snapshot([])
            data['scope']['account_alias'] = ''
            source.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                tasks.load_snapshot(source)

    def test_output_cannot_overwrite_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'snapshot.json'
            source.write_text(json.dumps(snapshot([item()])), encoding='utf-8')
            before = source.read_bytes()
            self.assertEqual(tasks.main(['diff', '--before', str(source), '--after', str(source), '--out', str(source)]), 2)
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
