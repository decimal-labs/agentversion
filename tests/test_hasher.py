"""Tests for canonical hashing (JCS-SHA256)."""

import json

import pytest

from agentversion.hasher import compute_and_set_hashes, hash_manifest, hash_surface


class TestHashSurface:
    """Test per-surface hashing."""

    def test_deterministic(self):
        """Same input produces same hash."""
        data = {"provider": "google", "model": "gemini-2.0-flash"}
        h1 = hash_surface(data)
        h2 = hash_surface(data)
        assert h1 == h2

    def test_starts_with_sha256(self):
        data = {"key": "value"}
        h = hash_surface(data)
        assert h.startswith("sha256:")

    def test_key_order_does_not_matter(self):
        """JCS canonicalizes key order, so different insertion order → same hash."""
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert hash_surface(d1) == hash_surface(d2)

    def test_different_data_different_hash(self):
        d1 = {"key": "value_a"}
        d2 = {"key": "value_b"}
        assert hash_surface(d1) != hash_surface(d2)


class TestHashManifest:
    """Test overall manifest hashing."""

    def test_uses_only_contract_block(self):
        """Metadata changes should NOT change the hash."""
        base = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
                "tool_registry": {"registry_version": "1", "registry_hash": "x", "tools": []},
                "workflow": {"graph_name": "g"},
                "output_contract": {"version": "1", "schema_hash": "x", "format": "text", "strict": False},
            },
            "tags": ["prod"],
            "description": "original",
        }

        modified = json.loads(json.dumps(base))
        modified["tags"] = ["staging", "test"]
        modified["description"] = "completely different description"

        assert hash_manifest(base) == hash_manifest(modified)

    def test_contract_change_changes_hash(self):
        base = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
            }
        }
        modified = json.loads(json.dumps(base))
        modified["contract"]["model_runtime"]["model"] = "gpt-5"

        assert hash_manifest(base) != hash_manifest(modified)

    def test_missing_contract_raises(self):
        with pytest.raises(KeyError):
            hash_manifest({"no_contract": True})


class TestComputeAndSetHashes:
    """Test the convenience function."""

    def test_sets_overall_hash(self):
        data = {
            "identity": {"overall_hash": "PLACEHOLDER"},
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "x", "model": "y"},
            },
        }
        result = compute_and_set_hashes(data)
        assert result["identity"]["overall_hash"].startswith("sha256:")
        assert result["identity"]["overall_hash"] != "PLACEHOLDER"
        assert result["identity"]["hash_algorithm"] == "jcs-sha256"

    def test_creates_identity_if_missing(self):
        data = {
            "contract": {
                "prompt_stack": {},
            }
        }
        result = compute_and_set_hashes(data)
        assert "identity" in result
        assert result["identity"]["overall_hash"].startswith("sha256:")

    def test_example_manifests_have_correct_hashes(self):
        """The example manifests should have hashes that match recomputation."""
        for name in ["finance-agent-v1.json", "finance-agent-v2.json"]:
            with open(f"examples/manifest/{name}") as f:
                data = json.load(f)
            declared = data["identity"]["overall_hash"]
            computed = hash_manifest(data)
            assert declared == computed, f"Hash mismatch in {name}: {declared} != {computed}"


class TestSkillRegistryHashing:
    """Test that skill_registry participates in overall_hash."""

    def test_skill_registry_contributes_to_overall_hash(self):
        """Manifests with different skill registries produce different hashes."""
        base = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
                "skill_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:aaa",
                    "skills": [{"name": "code-review", "hash": "sha256:bbb"}],
                },
            }
        }
        modified = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
                "skill_registry": {
                    "registry_version": "2",
                    "registry_hash": "sha256:ccc",
                    "skills": [
                        {"name": "code-review", "hash": "sha256:bbb"},
                        {"name": "sql-optimizer", "hash": "sha256:ddd"},
                    ],
                },
            }
        }
        assert hash_manifest(base) != hash_manifest(modified)

    def test_no_skill_registry_vs_with_skill_registry(self):
        """Adding a skill_registry surface changes the overall hash."""
        without_skills = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
            }
        }
        with_skills = {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "google", "model": "gemini"},
                "skill_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:aaa",
                    "skills": [],
                },
            }
        }
        assert hash_manifest(without_skills) != hash_manifest(with_skills)


class TestHashDomain:
    """Hash determinism under the inputs that actually break JCS/SHA: Unicode normalization +
    non-finite floats. The overall_hash (the moat) must be byte-identical across implementations."""

    def test_nfc_and_nfd_strings_hash_equal(self):
        import unicodedata
        # Composed 'café' (U+00E9) vs decomposed 'café' (U+0065 U+0301) are the SAME text — they must
        # produce the same surface hash, or two producers mint different identities for one agent.
        composed = {"persona": "café"}
        decomposed = {"persona": unicodedata.normalize("NFD", "café")}
        assert composed["persona"] != decomposed["persona"]  # different code points...
        assert hash_surface(composed) == hash_surface(decomposed)  # ...same hash

    def test_nfc_normalization_applies_to_keys_and_nested_values(self):
        import unicodedata
        nested = {"outer": {unicodedata.normalize("NFD", "naïve"): ["café", "x"]}}
        plain = {"outer": {"naïve": [unicodedata.normalize("NFD", "café"), "x"]}}
        assert hash_surface(nested) == hash_surface(plain)

    def test_ascii_hash_is_unchanged_by_normalization(self):
        # NFC of pure ASCII is a no-op, so existing (ASCII) manifest hashes are unaffected — pinned so a
        # future normalization tweak can't silently break the frozen vectors.
        data = {"provider": "google", "model": "gemini-2.0-flash", "temperature": 0.7}
        assert hash_surface(data) == (
            "sha256:" + __import__("hashlib").sha256(
                __import__("jcs").canonicalize(data)).hexdigest()
        )

    def test_nan_is_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            hash_surface({"temperature": float("nan")})

    def test_infinity_is_rejected(self):
        with pytest.raises(ValueError, match="non-finite"):
            hash_surface({"x": float("inf")})
        with pytest.raises(ValueError, match="non-finite"):
            hash_manifest({"contract": {"model_runtime": {"y": float("-inf")}}})

    def test_bool_is_not_treated_as_float(self):
        # bool is an int subclass; it must hash normally, not trip the float-domain check.
        assert hash_surface({"strict": True, "n": 3}).startswith("sha256:")
