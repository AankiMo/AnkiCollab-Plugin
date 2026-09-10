"""Tests for miscellaneous crowd_anki/representation modules that previously
had zero test references: benchmarking, json_serializable, deck_config."""

import pytest

from crowd_anki.representation import benchmarking
from crowd_anki.representation.json_serializable import JsonSerializable
from crowd_anki.representation.deck_config import DeckConfig


class TestBenchmarkStats:
    def setup_method(self):
        benchmarking.BenchmarkStats.stats.clear()

    def test_record_accumulates(self):
        benchmarking.BenchmarkStats.record("foo", 1.5)
        benchmarking.BenchmarkStats.record("foo", 0.5)
        stats = benchmarking.BenchmarkStats.stats["foo"]
        assert stats["calls"] == 2
        assert stats["total_time"] == pytest.approx(2.0)

    def test_benchmark_decorator_records_and_returns(self):
        calls = []

        @benchmarking.benchmark
        def answer():
            calls.append(1)
            return 42

        assert answer() == 42
        assert calls == [1]
        # One call recorded for the function (no positional args → plain name)
        assert benchmarking.BenchmarkStats.stats["answer"]["calls"] == 1


class _Concrete(JsonSerializable):
    readable_names = {"internal_key": "public_key"}

    def __init__(self, internal_key="value"):
        super().__init__()
        self.internal_key = internal_key


class TestJsonSerializable:
    def test_flatten_applies_readable_names(self):
        obj = _Concrete(internal_key="hello")
        flat = obj.flatten()
        assert flat["public_key"] == "hello"
        # mod/usn are filtered out by the export filter
        assert "mod" not in flat and "usn" not in flat

    def test_default_json_roundtrip(self):
        obj = _Concrete(internal_key="x")
        assert JsonSerializable.default_json(obj)["public_key"] == "x"

    def test_default_json_rejects_plain_dict(self):
        with pytest.raises(TypeError):
            JsonSerializable.default_json({"a": 1})

    def test_json_object_hook_passthrough_for_unknown_type(self):
        assert JsonSerializable.json_object_hook({"__type__": "Nope"}) == {
            "__type__": "Nope"
        }


class TestDeckConfig:
    def test_serialization_dict_includes_fields(self):
        cfg = DeckConfig({"name": "Default", "id": 1, "maxTaken": 60})
        out = cfg.serialization_dict()
        assert out["name"] == "Default"
        assert out["id"] == 1
