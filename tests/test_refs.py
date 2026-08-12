"""Tests for the manifest_ref URI scheme (§3c, added in v0.5.0)."""

from __future__ import annotations

import pytest

from agentversion.refs import (
    parse_manifest_ref,
    try_parse_manifest_ref,
)


class TestParseManifestRef:
    def test_agentversion_manifest_with_ulid(self):
        ref = parse_manifest_ref("agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K1")
        assert ref.scheme == "agentversion.manifest"
        assert ref.manifest_id == "amf_01HZK1A2B3C4D5E6F7G8H9J0K1"
        assert ref.hash is None
        assert ref.url is None
        assert ref.path is None

    def test_agentversion_manifest_with_slug_raises(self):
        with pytest.raises(ValueError, match="not canonical"):
            parse_manifest_ref("agentversion:manifest:amf_finance_v3")

    def test_agentversion_manifest_wrong_prefix_raises(self):
        with pytest.raises(ValueError, match="prefix"):
            parse_manifest_ref("agentversion:manifest:tsk_01HZK1A2B3C4D5E6F7G8H9J0K1")

    def test_agentversion_hash(self):
        ref = parse_manifest_ref("agentversion:hash:sha256:abcdef0123456789")
        assert ref.scheme == "agentversion.hash"
        assert ref.hash == "sha256:abcdef0123456789"
        assert ref.is_content_addressed()

    def test_agentversion_hash_different_algos(self):
        for algo in ["sha256", "sha512", "blake3"]:
            ref = parse_manifest_ref(f"agentversion:hash:{algo}:deadbeef")
            assert ref.scheme == "agentversion.hash"
            assert ref.hash == f"{algo}:deadbeef"

    def test_https(self):
        ref = parse_manifest_ref("https://example.com/manifests/finance.json")
        assert ref.scheme == "https"
        assert ref.url == "https://example.com/manifests/finance.json"
        assert ref.is_fetchable()
        assert not ref.is_content_addressed()

    def test_http(self):
        ref = parse_manifest_ref("http://localhost:8080/m.json")
        assert ref.scheme == "http"
        assert ref.is_fetchable()

    def test_file(self):
        ref = parse_manifest_ref("file:///tmp/manifest.json")
        assert ref.scheme == "file"
        assert ref.path == "/tmp/manifest.json"
        assert ref.is_fetchable()

    def test_bare_id_rejected(self):
        # No scheme prefix → reject.
        with pytest.raises(ValueError, match="doesn't match"):
            parse_manifest_ref("amf_01HZK1A2B3C4D5E6F7G8H9J0K1")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_manifest_ref("")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="doesn't match"):
            parse_manifest_ref("not a ref")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_manifest_ref(123)  # type: ignore[arg-type]


class TestTryParseManifestRef:
    def test_returns_ref_on_success(self):
        ref = try_parse_manifest_ref("agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K1")
        assert ref is not None
        assert ref.scheme == "agentversion.manifest"

    def test_returns_none_on_failure(self):
        assert try_parse_manifest_ref("garbage") is None
        assert try_parse_manifest_ref("") is None
        assert try_parse_manifest_ref("amf_01HZK1A2B3C4D5E6F7G8H9J0K1") is None  # no scheme


class TestValidatorIntegration:
    """The semantic validator should warn on bare IDs and error on garbage."""

    def _minimal_manifest_with_subagent(self, manifest_ref: str) -> dict:
        return {
            "spec_version": "0.5.0",
            "kind": "agent_manifest",
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "agent_name": "test",
            "version_label": "v1",
            "created_at": "2026-01-01T00:00:00Z",
            "identity": {"overall_hash": "sha256:abc", "hash_algorithm": "jcs-sha256"},
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "openai", "model": "gpt-4o"},
                "tool_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:reg",
                    "tools": [],
                },
                "subagents": [
                    {
                        "name": "child",
                        "version": "1",
                        "hash": "sha256:c1",
                        "manifest_ref": manifest_ref,
                    }
                ],
                "workflow": {"graph_name": "g"},
                "output_contract": {
                    "version": "1", "schema_hash": "sha256:o",
                    "format": "text", "strict": False,
                },
            },
        }

    def test_agentversion_uri_no_issues(self):
        from agentversion.validator import validate_manifest

        data = self._minimal_manifest_with_subagent(
            "agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K2"
        )
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "malformed_manifest_ref" not in codes

    def test_bare_id_errors(self):
        from agentversion.validator import validate_manifest

        data = self._minimal_manifest_with_subagent("amf_01HZK1A2B3C4D5E6F7G8H9J0K9")
        result = validate_manifest(data, check_hash=False)
        assert result.valid is False
        codes = {i.code for i in result.errors}
        assert "malformed_manifest_ref" in codes

    def test_garbage_errors(self):
        from agentversion.validator import validate_manifest

        data = self._minimal_manifest_with_subagent("totally not a ref")
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.errors}
        assert "malformed_manifest_ref" in codes

    def test_hash_uri_no_issues(self):
        from agentversion.validator import validate_manifest

        data = self._minimal_manifest_with_subagent("agentversion:hash:sha256:abcdef")
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "malformed_manifest_ref" not in codes
