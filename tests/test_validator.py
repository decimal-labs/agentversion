"""Tests for semantic validation."""



from agentversion.validator import validate_manifest, validate_manifest_file


def _valid_manifest() -> dict:
    """Return a valid manifest dict with correct computed hash."""
    from agentversion.hasher import compute_and_set_hashes

    data = {
        "spec_version": "0.1.0",
        "kind": "agent_manifest",
        "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "agent_name": "test-agent",
        "version_label": "v1",
        "created_at": "2026-03-10T10:00:00Z",
        "identity": {
            "overall_hash": "PLACEHOLDER",
            "hash_algorithm": "jcs-sha256",
        },
        "contract": {
            "prompt_stack": {
                "system_prompt": {
                    "id": "prompt_sys",
                    "version": "1",
                    "hash": "sha256:aaa",
                }
            },
            "model_runtime": {
                "provider": "google",
                "model": "gemini-2.0-flash",
            },
            "tool_registry": {
                "registry_version": "1",
                "registry_hash": "sha256:bbb",
                "tools": [
                    {"name": "tool_a", "version": "1", "hash": "sha256:111"},
                    {"name": "tool_b", "version": "1", "hash": "sha256:222"},
                ],
            },
            "workflow": {"graph_name": "test-graph"},
            "output_contract": {
                "version": "1",
                "schema_hash": "sha256:ddd",
                "format": "text",
                "strict": False,
            },
        },
    }
    compute_and_set_hashes(data)
    return data


class TestValidManifest:
    def test_valid_passes(self):
        result = validate_manifest(_valid_manifest())
        assert result.valid is True
        assert len(result.errors) == 0
        assert result.manifest is not None

    def test_valid_example_files(self):
        for name in ["finance-agent-v1.json", "finance-agent-v2.json"]:
            result = validate_manifest_file(f"examples/manifest/{name}")
            assert result.valid is True, f"{name} should be valid: {result.issues}"


class TestStructuralValidation:
    def test_missing_agent_name(self):
        data = _valid_manifest()
        del data["agent_name"]
        result = validate_manifest(data)
        assert result.valid is False
        assert any(i.code == "pydantic_validation" for i in result.issues)

    def test_wrong_kind(self):
        data = _valid_manifest()
        data["kind"] = "wrong"
        result = validate_manifest(data)
        assert result.valid is False


class TestSelfReferencingParent:
    def test_self_referencing_parent_is_error(self):
        data = _valid_manifest()
        data["parent_manifest_id"] = data["manifest_id"]
        result = validate_manifest(data)
        assert result.valid is False
        assert any(i.code == "self_referencing_parent" for i in result.issues)

    def test_null_parent_is_fine(self):
        data = _valid_manifest()
        data["parent_manifest_id"] = None
        result = validate_manifest(data)
        assert result.valid is True


class TestDuplicateToolHash:
    def test_duplicate_hash_warns(self):
        data = _valid_manifest()
        # Make both tools have the same hash
        data["contract"]["tool_registry"]["tools"][1]["hash"] = (
            data["contract"]["tool_registry"]["tools"][0]["hash"]
        )
        result = validate_manifest(data, check_hash=False)
        assert result.valid is True  # warning, not error
        assert any(i.code == "duplicate_tool_hash" for i in result.warnings)


class TestHashVerification:
    def test_hash_mismatch_warns(self):
        data = _valid_manifest()
        data["identity"]["overall_hash"] = "sha256:wrong_hash"
        result = validate_manifest(data, check_hash=True)
        assert result.valid is True  # warning, not error
        assert any(i.code == "hash_mismatch" for i in result.warnings)

    def test_correct_hash_no_warning(self):
        data = _valid_manifest()
        result = validate_manifest(data, check_hash=True)
        hash_issues = [i for i in result.issues if i.code == "hash_mismatch"]
        assert len(hash_issues) == 0

    def test_skip_hash_check(self):
        data = _valid_manifest()
        data["identity"]["overall_hash"] = "sha256:wrong"
        result = validate_manifest(data, check_hash=False)
        hash_issues = [i for i in result.issues if i.code == "hash_mismatch"]
        assert len(hash_issues) == 0


class TestUnsupportedHashAlgorithm:
    def test_non_standard_algorithm_warns(self):
        data = _valid_manifest()
        data["identity"]["hash_algorithm"] = "md5"
        result = validate_manifest(data, check_hash=False)
        assert any(i.code == "unsupported_hash_algorithm" for i in result.warnings)


class TestFileValidation:
    def test_file_not_found(self, tmp_path):
        result = validate_manifest_file(tmp_path / "nonexistent.json")
        assert result.valid is False
        assert any(i.code == "file_not_found" for i in result.issues)

    def test_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")
        result = validate_manifest_file(str(bad_file))
        assert result.valid is False
        assert any(i.code == "json_parse_error" for i in result.issues)


class TestAttestationLinkage:
    """An attestation must cover THIS manifest: signed_payload_hash == overall_hash. Cryptographic
    signature verification stays out of scope (delegated to a verifier), but the no-crypto integrity
    linkage is enforced so a copy-pasted/tampered attestation can't ride along inertly."""

    def _att(self, payload_hash: str) -> dict:
        return {
            "signer": "sigstore:github.com/decimalai/release@main",
            "algorithm": "cosign-rsa-sha256",
            "signature": "ZmFrZQ==",  # base64 'fake' — the bytes are NOT verified here, by design
            "signed_payload_hash": payload_hash,
            "signed_at": "2026-03-10T10:05:00Z",
        }

    def test_matching_attestation_passes(self):
        data = _valid_manifest()
        data["identity"]["attestations"] = [self._att(data["identity"]["overall_hash"])]
        result = validate_manifest(data)
        assert result.valid is True
        assert not any(i.code == "attestation_payload_mismatch" for i in result.issues)

    def test_mismatched_attestation_is_error(self):
        data = _valid_manifest()
        data["identity"]["attestations"] = [self._att("sha256:" + "0" * 64)]
        result = validate_manifest(data)
        assert result.valid is False
        assert any(i.code == "attestation_payload_mismatch" for i in result.errors)
