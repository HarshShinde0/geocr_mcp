"""Unit tests for shared helpers."""

import datetime
import json
import pytest
from geocr_mcp_server import common


class TestResolveJsonldInput:
    def test_content_wins(self, valid_geocroissant):
        result = common.resolve_jsonld_input(jsonld_content=json.dumps(valid_geocroissant))
        assert result == valid_geocroissant

    def test_path_resolved_absolute(self, valid_geocroissant_file):
        result = common.resolve_jsonld_input(jsonld_path=valid_geocroissant_file)
        assert str(result).endswith('metadata.json')

    def test_url_passthrough(self):
        url = 'https://example.com/metadata.json'
        assert common.resolve_jsonld_input(jsonld_url=url) == url

    def test_no_input_raises(self):
        with pytest.raises(ValueError, match='No input'):
            common.resolve_jsonld_input()

    def test_multiple_inputs_raise(self, tmp_path):
        f = tmp_path / 'm.json'
        f.write_text('{}')
        with pytest.raises(ValueError, match='Multiple inputs'):
            common.resolve_jsonld_input(jsonld_path=str(f), jsonld_url='https://x')

    def test_bad_json_content(self):
        with pytest.raises(ValueError, match='not valid JSON'):
            common.resolve_jsonld_input(jsonld_content='{oops')

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            common.resolve_jsonld_input(jsonld_path='/no/such/file.json')


class TestToJsonSafe:
    def test_primitives(self):
        assert common.to_json_safe(1) == 1
        assert common.to_json_safe('a') == 'a'
        assert common.to_json_safe(None) is None
        assert common.to_json_safe(True) is True

    def test_datetime(self):
        dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
        assert common.to_json_safe(dt) == '2024-01-02T03:04:05'

    def test_nested_containers(self):
        value = {'a': [1, {'b': datetime.date(2020, 12, 31)}]}
        assert common.to_json_safe(value) == {'a': [1, {'b': '2020-12-31'}]}

    def test_language_value(self):
        assert common._language_value({'en': 'hello'}) == 'hello'
        assert common._language_value('plain') == 'plain'


class TestSecureOutputPath:
    def test_traversal_blocked(self, monkeypatch, tmp_path):
        monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))
        path = common.secure_output_path('../../etc/passwd.json')
        assert path.parent == tmp_path
        assert path.name == 'passwd.json'

    def test_default_dir_created(self, monkeypatch):
        monkeypatch.delenv('GEOCR_OUTPUT_DIR', raising=False)
        path = common.secure_output_path('out.json', output_dir=None)
        assert path.name == 'out.json'
        assert path.parent.exists()


class TestWriteJsonLd:
    def test_roundtrip(self, tmp_path, valid_geocroissant):
        path = common.write_json_ld(valid_geocroissant, tmp_path / 'doc.json')
        assert json.loads(path.read_text(encoding='utf-8')) == valid_geocroissant
