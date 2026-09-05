import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))

import prepare_data  # noqa: E402


def test_missing_dataset_exits_2_and_names_licence(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(prepare_data, "DATASETS_DIR", tmp_path)
    code = prepare_data.main(["--dataset", "sh17"])
    err = capsys.readouterr().err
    assert code == 2
    assert "CC BY-NC-SA" in err and "kaggle.com" in err


def test_present_dataset_is_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(prepare_data, "DATASETS_DIR", tmp_path)
    ledger = tmp_path / "datasets.md"
    ledger.write_text("# ledger\n\n## Licence implications\n")
    monkeypatch.setattr(prepare_data, "LEDGER", ledger)
    (tmp_path / "mvtec" / "bottle").mkdir(parents=True)
    (tmp_path / "mvtec" / "screw").mkdir()
    (tmp_path / "mvtec" / "bottle" / "a.png").write_bytes(b"x")
    assert prepare_data.main(["--dataset", "mvtec"]) == 0
    text = ledger.read_text()
    assert "MVTec" in text and "(verified)" in text and "CC BY-NC-SA 4.0" in text
