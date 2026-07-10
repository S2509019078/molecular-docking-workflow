from dockflow.cache import build_payload, manifest_valid, write_manifest


def test_manifest_invalidates_when_input_changes(tmp_path):
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    manifest = tmp_path / "manifest.json"
    source.write_text("first", encoding="utf-8")
    output.write_text("result", encoding="utf-8")
    payload = build_payload(inputs={"source": source}, parameters={"value": 1})
    write_manifest(manifest, payload, [output])
    assert manifest_valid(manifest, payload, [output])
    source.write_text("second", encoding="utf-8")
    changed = build_payload(inputs={"source": source}, parameters={"value": 1})
    assert not manifest_valid(manifest, changed, [output])


def test_manifest_invalidates_when_parameters_change(tmp_path):
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    manifest = tmp_path / "manifest.json"
    source.write_text("input", encoding="utf-8")
    output.write_text("result", encoding="utf-8")
    payload = build_payload(inputs={"source": source}, parameters={"exhaustiveness": 8})
    write_manifest(manifest, payload, [output])
    changed = build_payload(inputs={"source": source}, parameters={"exhaustiveness": 32})
    assert not manifest_valid(manifest, changed, [output])
