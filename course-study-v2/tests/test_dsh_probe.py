import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'dsh_probe.py'
spec = importlib.util.spec_from_file_location('dsh_probe', SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SKILL_TEXT = '---\nname: course-study-v2\ndescription: test\n---\nbody\n'


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        (self.project / '.git').mkdir(parents=True)
        self.dsh = self.base / 'dsh-home'
        self.agents = self.base / 'agents-home'
        self.source = self.base / 'source'
        self.write(self.source / 'SKILL.md', SKILL_TEXT)

    @staticmethod
    def write(path, text):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding='utf-8')

    def install(self, root, text=SKILL_TEXT):
        target = Path(root) / 'course-study-v2' / 'SKILL.md'
        self.write(target, text)
        return target

    def report(self, tools=None, source=None):
        return probe.build_report(cwd=self.project, tools=tools,
                                  source_root=source or self.source,
                                  dsh_home=self.dsh, agents_home=self.agents)

    def tool_file(self, names, name='tools.json'):
        path = self.base / name
        self.write(path, json.dumps(names))
        return path

    def run_main(self, extra=()):
        args = ['--cwd', str(self.project), '--dsh-home', str(self.dsh),
                '--agents-home', str(self.agents), '--source', str(self.source), *extra]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return probe.main(args)

    def test_project_root_is_the_nearest_git_ancestor(self):
        nested = self.project / 'a' / 'b'
        nested.mkdir(parents=True)
        self.assertEqual(probe.project_root(nested), self.project.resolve())

    def test_without_git_the_cwd_is_the_project_root(self):
        loose = self.base / 'loose'
        loose.mkdir()
        self.assertEqual(probe.project_root(loose), loose.resolve())

    def test_project_copy_outranks_user_copy(self):
        self.install(self.project / '.agents' / 'skills')
        self.install(self.agents / 'skills')
        result = self.report()
        self.assertEqual(result['discovery']['winner']['source'], 'project-agents')
        self.assertEqual(result['discovery']['winner']['rank'], 200)
        self.assertEqual(len(result['discovery']['copies']), 2)

    def test_user_agents_root_is_reported_when_it_is_the_only_copy(self):
        installed = self.install(self.agents / 'skills')
        result = self.report()
        self.assertEqual(result['discovery']['winner']['source'], 'user-agents')
        self.assertEqual(result['discovery']['winner']['rank'], 500)
        self.assertEqual(result['discovery']['winner']['skill_file'], str(installed))

    def test_flat_skill_file_is_discovered(self):
        self.write(self.dsh / 'skills' / 'course-study-v2.md', SKILL_TEXT)
        result = self.report()
        self.assertEqual(result['discovery']['winner']['kind'], 'flat')
        self.assertEqual(result['discovery']['winner']['source'], 'user-dsh')

    def test_custom_root_is_scanned_between_project_and_user_roots(self):
        custom = self.base / 'custom-skills'
        self.install(custom)
        self.install(self.agents / 'skills')
        result = probe.build_report(cwd=self.project, source_root=self.source, dsh_home=self.dsh,
                                    agents_home=self.agents, custom=[str(custom)])
        self.assertEqual(result['discovery']['winner']['source'], 'custom')

    def test_identical_install_reports_no_drift(self):
        self.install(self.agents / 'skills')
        self.assertEqual(self.report()['discovery']['drift'], [])

    def test_modified_install_is_reported_as_drift(self):
        installed = self.install(self.agents / 'skills', SKILL_TEXT + 'edited\n')
        result = self.report()
        self.assertEqual(len(result['discovery']['drift']), 1)
        self.assertEqual(result['discovery']['drift'][0]['source'], 'user-agents')
        self.assertFalse(result['discovery']['drift'][0]['matches_source'])
        self.assertEqual(result['discovery']['drift'][0]['skill_file'], str(installed))

    def test_missing_tool_list_is_unknown_not_absent(self):
        capability = self.report()['capability']
        self.assertEqual(self.report()['tools']['verdict'], 'unknown')
        self.assertFalse(self.report()['tools']['provided'])
        self.assertEqual(capability['browser_channel'], 'unknown')
        self.assertEqual(capability['live_course_work'], 'unknown')

    def test_plain_tool_list_has_no_browser_channel(self):
        result = self.report(tools=['read', 'write', 'pwsh', 'web_fetch'])
        self.assertEqual(result['tools']['verdict'], 'none')
        self.assertEqual(result['capability']['live_course_work'], 'blocked')

    def test_browser_shaped_mcp_tool_is_only_a_candidate(self):
        result = self.report(tools=['read', 'mcp__playwright__browser_click'])
        self.assertEqual(result['tools']['verdict'], 'candidate')
        candidate = result['tools']['browser_candidates'][0]
        self.assertEqual(candidate['namespace'], 'playwright')
        self.assertFalse(candidate['verified'])
        self.assertEqual(result['capability']['live_course_work'], 'needs-verification')
        self.assertFalse(result['capability']['verified'])

    def test_native_browser_shaped_tool_is_a_candidate(self):
        result = self.report(tools=['browser_navigate'])
        self.assertEqual(result['tools']['verdict'], 'candidate')
        self.assertEqual(result['tools']['browser_candidates'][0]['namespace'], 'native')

    def test_tool_entry_without_a_name_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.tool_names([{'description': 'unnamed'}])

    def test_bad_tool_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.tool_names({'tools': 'nope'})

    def test_report_declares_no_network_or_side_effects(self):
        flags = self.report()['probe']
        self.assertFalse(flags['network_used'])
        self.assertFalse(flags['browser_opened'])
        self.assertFalse(flags['environment_changed'])

    def test_main_exit_codes(self):
        plain = self.tool_file(['read', 'pwsh'], 'plain.json')
        browser = self.tool_file(['mcp__playwright__browser_click'], 'browser.json')
        self.assertEqual(self.run_main([]), 0)
        self.assertEqual(self.run_main(['--tools', str(plain)]), 1)
        self.assertEqual(self.run_main(['--tools', str(browser)]), 0)
        self.assertEqual(self.run_main(['--tools', str(plain), '--allow-offline']), 0)

    def test_manifest_drift_finds_hash_and_missing_files(self):
        target = self.agents / 'skills' / 'course-study-v2'
        self.write(target / 'SKILL.md', SKILL_TEXT)
        self.write(self.source / 'scripts' / 'same.py', 'print(1)\n')
        self.write(target / 'scripts' / 'same.py', 'print(2)\n')
        self.write(self.source / 'scripts' / 'gone.py', 'print(3)\n')
        manifest = {'version': '1.0.0', 'files': [
            {'path': 'SKILL.md', 'sha256': hashlib.sha256((target / 'SKILL.md').read_bytes()).hexdigest()},
            {'path': 'scripts/same.py', 'sha256': hashlib.sha256((target / 'scripts/same.py').read_bytes()).hexdigest()},
            {'path': 'scripts/gone.py', 'sha256': '0' * 64},
        ]}
        self.write(target / 'package-manifest.json', json.dumps(manifest))
        result = self.report()
        kinds = {(item['kind'], item['path']) for item in result['discovery']['manifest_drift']}
        self.assertIn(('manifest-hash-mismatch', 'scripts/same.py'), kinds)
        self.assertIn(('manifest-missing-in-install', 'scripts/gone.py'), kinds)
        self.assertIn('user-agents', probe.summary(result)['drift'])
        self.assertEqual(probe.summary(result)['manifest_drift_files'], 2)

    def test_manifest_self_check_detects_tampering_when_source_is_the_install(self):
        target = self.agents / 'skills' / 'course-study-v2'
        self.write(target / 'SKILL.md', SKILL_TEXT)
        manifest = {'version': '1.0.1', 'files': [
            {'path': 'SKILL.md', 'sha256': hashlib.sha256(SKILL_TEXT.encode()).hexdigest()},
        ]}
        self.write(target / 'package-manifest.json', json.dumps(manifest))
        self.write(target / 'SKILL.md', SKILL_TEXT + 'tampered\n')
        result = probe.build_report(cwd=self.project, source_root=target,
                                    dsh_home=self.dsh, agents_home=self.agents)
        kinds = {(item['kind'], item['path']) for item in result['discovery']['manifest_drift']}
        self.assertIn(('manifest-hash-mismatch', 'SKILL.md'), kinds)
        self.assertTrue(probe.summary(result)['source_is_installed_copy'])
        self.assertEqual(probe.summary(result)['manifest_drift_files'], 1)

    def test_source_is_installed_copy_is_reported(self):
        target = self.install(self.agents / 'skills')
        self.assertTrue(probe.summary(probe.build_report(
            cwd=self.project, source_root=target.parent, dsh_home=self.dsh,
            agents_home=self.agents))['source_is_installed_copy'])
        self.assertFalse(probe.summary(self.report())['source_is_installed_copy'])

    def test_require_discovered_exits_five_without_a_copy(self):
        self.assertEqual(self.run_main(['--require-discovered']), probe.EXIT_NOT_DISCOVERED)
        self.install(self.agents / 'skills')
        self.assertEqual(self.run_main(['--require-discovered']), 0)

    def test_require_winner_checks_the_winning_copy(self):
        self.install(self.agents / 'skills')
        good = self.agents / 'skills' / 'course-study-v2'
        self.assertEqual(self.run_main(['--require-winner', str(good)]), 0)
        self.assertEqual(self.run_main(['--require-winner', str(self.base / 'other')]), probe.EXIT_WRONG_WINNER)

    def test_manifest_drift_is_empty_when_files_match(self):
        target = self.agents / 'skills' / 'course-study-v2'
        self.write(target / 'SKILL.md', SKILL_TEXT)
        self.write(self.source / 'scripts' / 'same.py', 'print(1)\n')
        self.write(target / 'scripts' / 'same.py', 'print(1)\n')
        manifest = {'version': '1.0.0', 'files': [{'path': 'scripts/same.py',
                    'sha256': hashlib.sha256((target / 'scripts/same.py').read_bytes()).hexdigest()}]}
        self.write(target / 'package-manifest.json', json.dumps(manifest))
        result = self.report()
        self.assertEqual(result['discovery']['manifest_drift'], [])
        self.assertEqual(probe.summary(result)['drift'], [])

    def test_manifest_rejects_traversal_and_invalid_shapes(self):
        target = self.agents / 'skills' / 'course-study-v2'
        self.install(self.agents / 'skills')
        for entry in ('../outside.txt', '/outside.txt', 'C:/outside.txt', 'scripts\\bad.py'):
            self.write(target / 'package-manifest.json', json.dumps({'files': [{'path': entry}]}))
            drift, _ = probe.manifest_drift(target, self.source)
            self.assertEqual(drift[0]['kind'], 'manifest-invalid-entry')
        for payload in ([], {}, {'files': []}, {'files': 'bad'}):
            self.write(target / 'package-manifest.json', json.dumps(payload))
            self.assertEqual(probe.manifest_drift(target, self.source)[0][0]['kind'], 'manifest-invalid')

    def test_require_clean_detects_tampering_even_from_the_install(self):
        target = self.agents / 'skills' / 'course-study-v2'
        self.install(self.agents / 'skills')
        self.write(target / 'package-manifest.json', json.dumps({'version': 'test', 'files': [
            {'path': 'SKILL.md', 'sha256': hashlib.sha256((target / 'SKILL.md').read_bytes()).hexdigest()}]}))
        self.assertEqual(self.run_main(['--require-clean']), 0)
        self.write(target / 'SKILL.md', SKILL_TEXT + 'changed')
        self.assertEqual(self.run_main(['--source', str(target), '--require-clean']), probe.EXIT_DRIFT)

    def test_require_clean_refuses_a_copy_without_a_manifest(self):
        self.install(self.agents / 'skills')
        self.assertEqual(self.run_main(['--require-clean']), probe.EXIT_DRIFT)

    def test_bad_tool_file_returns_two(self):
        bad = self.base / 'bad.json'
        self.write(bad, 'not json')
        self.assertEqual(self.run_main(['--tools', str(bad)]), 2)

    def test_out_file_holds_the_full_report_without_leftovers(self):
        out = self.base / 'records' / 'probe.json'
        self.install(self.agents / 'skills', SKILL_TEXT + 'edited\n')
        self.assertEqual(self.run_main(['--out', str(out)]), 0)
        data = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['discovery']['winner']['source'], 'user-agents')
        self.assertTrue(data['discovery']['drift'])
        self.assertFalse(list(out.parent.glob('*.tmp')))

    def test_existing_record_is_kept_unless_forced(self):
        out = self.base / 'records' / 'probe.json'
        self.write(out, 'keep me')
        self.assertEqual(self.run_main(['--out', str(out)]), 2)
        self.assertEqual(out.read_text(encoding='utf-8'), 'keep me')
        self.assertEqual(self.run_main(['--out', str(out), '--force']), 0)
        self.assertNotEqual(out.read_text(encoding='utf-8'), 'keep me')
        self.assertFalse(list(out.parent.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
