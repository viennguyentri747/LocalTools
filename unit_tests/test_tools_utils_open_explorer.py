import dev.dev_common.tools_utils as tools_utils


class _Result:
    def __init__(self, returncode: int):
        self.returncode = returncode


def test_open_path_in_explorer_treats_wsl_exit_code_one_as_success(monkeypatch, tmp_path):
    calls, logs = [], []
    test_file = tmp_path / "sample.txt"
    test_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tools_utils, "run_shell", lambda cmd, **kwargs: calls.append(cmd) or _Result(1))
    monkeypatch.setattr(tools_utils, "get_normalized_path", lambda path, target_platform=None: "C:\\fake\\sample.txt")
    monkeypatch.setattr(tools_utils, "is_platform_windows", lambda: False)
    monkeypatch.setattr(tools_utils.shutil, "which", lambda command: f"/usr/bin/{command}" if command == "explorer.exe" else None)
    monkeypatch.setattr(tools_utils, "LOG", lambda message, *args, **kwargs: logs.append(str(message)))

    tools_utils.open_path_in_explorer(test_file)

    assert len(calls) == 1
    assert any("treated as success" in message for message in logs)


def test_open_path_in_explorer_normalizes_forward_slashes_for_explorer(monkeypatch, tmp_path):
    calls = []
    test_file = tmp_path / "sample.txt"
    test_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tools_utils, "run_shell", lambda cmd, **kwargs: calls.append(cmd) or _Result(0))
    monkeypatch.setattr(tools_utils, "get_normalized_path", lambda path, target_platform=None: "C:/fake/sample.txt")
    monkeypatch.setattr(tools_utils.shutil, "which", lambda command: f"/usr/bin/{command}" if command == "explorer.exe" else None)
    monkeypatch.setattr(tools_utils, "LOG", lambda *args, **kwargs: None)

    tools_utils.open_path_in_explorer(test_file)

    assert len(calls) == 1
    assert calls[0][1] == "/select,C:\\fake\\sample.txt"


def test_open_path_in_explorer_warns_when_explorer_is_missing(monkeypatch, tmp_path):
    calls, logs = [], []
    test_file = tmp_path / "sample.txt"
    test_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tools_utils.shutil, "which", lambda command: None)
    monkeypatch.setattr(tools_utils, "run_shell", lambda cmd, **kwargs: calls.append(cmd) or _Result(0))
    monkeypatch.setattr(tools_utils, "get_normalized_path", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected path conversion")))
    monkeypatch.setattr(tools_utils, "LOG", lambda message, *args, **kwargs: logs.append(str(message)))

    tools_utils.open_path_in_explorer(test_file)

    assert calls == []
    assert any("Cannot open Explorer" in message for message in logs)
