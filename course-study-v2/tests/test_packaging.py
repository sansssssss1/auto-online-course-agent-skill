import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'package_skill.py'
spec = importlib.util.spec_from_file_location('package_skill', SCRIPT)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'SKILL.md').write_text('---\nname: course-study-v2\ndescription: test\n---\n', encoding='utf-8')
        (self.source / 'local').mkdir()
        (self.source / 'local' / 'runtime.json').write_text('{"private":"PRIVATE_LOCATION"}', encoding='utf-8')
        (self.source / 'local' / 'credentials.local.json').write_text('{"private":"DO_NOT_COPY"}', encoding='utf-8')
        (self.source / 'runs').mkdir()
        (self.source / 'runs' / 'state.json').write_text('{"private":"RUNTIME_STATE"}', encoding='utf-8')

    def call(self, args):
        with patch.object(package, 'ROOT', self.source), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return package.main(args)

    def test_public_export_excludes_private_data(self):
        output = self.base / 'public'
        self.assertEqual(self.call(['export', '--out', str(output)]), 0)
        self.assertFalse((output / 'local').exists())
        self.assertFalse((output / 'runs').exists())
        self.assertTrue((output / 'SKILL.md').exists())

    def test_install_copies_location_metadata_but_no_credentials(self):
        output = self.base / 'course-study-v2'
        self.assertEqual(self.call(['install', '--target', str(output), '--include-local']), 0)
        self.assertTrue((output / 'local' / 'runtime.json').exists())
        self.assertFalse((output / 'local' / 'credentials.local.json').exists())
        self.assertFalse((output / 'runs').exists())

    def test_nonempty_target_is_untouched(self):
        output = self.base / 'course-study-v2'
        output.mkdir()
        original = output / 'state.json'
        original.write_text('existing data', encoding='utf-8')
        self.assertEqual(self.call(['install', '--target', str(output)]), 2)
        self.assertEqual(original.read_text(), 'existing data')
        self.assertEqual(len(list(output.iterdir())), 1)

    def test_denylist_blocks_before_output(self):
        (self.source / 'references').mkdir()
        (self.source / 'references' / 'unsafe.md').write_text('PRIVATE_MARKER', encoding='utf-8')
        denylist = self.base / 'deny.json'
        denylist.write_text(json.dumps(['PRIVATE_MARKER']), encoding='utf-8')
        output = self.base / 'public'
        self.assertEqual(self.call(['export', '--out', str(output), '--denylist', str(denylist)]), 2)
        self.assertFalse(output.exists())

    def test_public_export_skips_pytest_cache(self):
        tests = self.source / 'tests'
        cache = tests / '.pytest_cache' / 'v'
        cache.mkdir(parents=True)
        (cache / 'nodeids').write_text('[]', encoding='utf-8')
        (tests / 'test_sample.py').write_text('x = 1\n', encoding='utf-8')
        output = self.base / 'public-cache'
        self.assertEqual(self.call(['export', '--out', str(output)]), 0)
        self.assertFalse((output / 'tests' / '.pytest_cache').exists())
        self.assertTrue((output / 'tests' / 'test_sample.py').exists())

    def test_cannot_target_an_old_skill_name(self):
        output = self.base / 'course-homework'
        self.assertEqual(self.call(['install', '--target', str(output)]), 2)
        self.assertFalse(output.exists())

    def test_extensionless_files_are_scanned(self):
        (self.source / 'LICENSE').write_text('PRIVATE_MARKER', encoding='utf-8')
        findings = package.public_scan([(self.source / 'LICENSE', Path('LICENSE'))], ['PRIVATE_MARKER'])
        self.assertEqual(findings, [{'path': 'LICENSE', 'kind': 'local-denylist-match'}])

    def test_credentials_and_session_urls_are_blocked_without_echoing_values(self):
        path = self.source / 'unsafe.md'
        literal_value = 'non' + 'placeholder-value'
        path.write_text('pass' + 'word = ' + repr(literal_value) + '\nhttps://example.invalid/?cpi=' + str(98765), encoding='utf-8')
        findings = package.public_scan([(path, Path('unsafe.md'))], [])
        self.assertEqual({item['kind'] for item in findings}, {'credential-literal', 'private-session-url'})
        self.assertNotIn(literal_value, json.dumps(findings))

    def test_placeholders_are_allowed(self):
        path = self.source / 'example.md'
        path.write_text('password = "<password>"\nusername = "YOUR_USERNAME"\nhttps://example.invalid/?signature=PRIVATE&cpi=123&enc={enc}', encoding='utf-8')
        self.assertEqual(package.public_scan([(path, Path('example.md'))], []), [])

    def test_state_labels_and_empty_query_fields_are_not_secrets(self):
        path = self.source / 'safe.js'
        path.write_text("state = needsSetup ? 'need-set-password' : 'sms-rejected';\n// `https://example.invalid/?enc=`", encoding='utf-8')
        self.assertEqual(package.public_scan([(path, Path('safe.js'))], []), [])

    def test_binary_is_blocked(self):
        path = self.source / 'capture.png'
        path.write_bytes(bytes([137, 80, 78, 71]))
        self.assertEqual(package.public_scan([(path, Path('capture.png'))], [])[0]['kind'], 'unreviewed-binary')

    def test_nul_containing_data_is_blocked(self):
        path = self.source / 'hidden.txt'
        path.write_bytes('private'.encode('utf-16-le'))
        self.assertEqual(package.public_scan([(path, Path('hidden.txt'))], [])[0]['kind'], 'unreviewed-binary')

    def test_named_denylist_object_is_supported(self):
        denylist = self.base / 'deny.json'
        denylist.write_text(json.dumps({'values': ['PRIVATE_MARKER']}), encoding='utf-8')
        self.assertEqual(self.call(['export', '--out', str(self.base / 'public'), '--denylist', str(denylist)]), 0)


if __name__ == '__main__':
    unittest.main()
