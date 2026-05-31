import dev.dev_common.core_independent_utils as core_utils


class _Result:
    def __init__(self, stdout: str):
        self.stdout = stdout


def test_convert_wsl_to_win_path_logs_raw_windows_path(monkeypatch):
    logs = []
    monkeypatch.setattr(core_utils, "run_shell", lambda *args, **kwargs: _Result("C:\\Users\\Vien.Nguyen\\temp\\acu_logs\n"))
    monkeypatch.setattr(core_utils, "is_platform_windows", lambda: False)
    monkeypatch.setattr(core_utils, "format_path_for_display", lambda p: "/mnt/c/Users/Vien.Nguyen/temp/acu_logs" if "C:" in str(p) else str(p))
    monkeypatch.setattr(core_utils, "LOG", lambda message, *args, **kwargs: logs.append(str(message)))

    result = core_utils.convert_wsl_to_win_path(core_utils.Path("/mnt/c/Users/Vien.Nguyen/temp/acu_logs"))

    assert result == "C:\\Users\\Vien.Nguyen\\temp\\acu_logs"
    assert any("Windows path: C:\\Users\\Vien.Nguyen\\temp\\acu_logs" in message for message in logs)


def test_get_normalized_path_windows_logs_raw(monkeypatch):
    logs = []
    monkeypatch.setattr(core_utils, "convert_wsl_to_win_path", lambda p: "C:\\Users\\Vien.Nguyen\\temp\\acu_logs")
    monkeypatch.setattr(core_utils, "format_path_for_display", lambda p: "/mnt/c/Users/Vien.Nguyen/temp/acu_logs" if "C:" in str(p) else str(p))
    monkeypatch.setattr(core_utils, "LOG", lambda message, *args, **kwargs: logs.append(str(message)))

    normalized = core_utils.get_normalized_path(
        "/mnt/c/Users/Vien.Nguyen/temp/acu_logs",
        target_platform=core_utils.ETargetPlatform.WINDOWS,
        log_label="log dir",
    )

    assert str(normalized) == "C:\\Users\\Vien.Nguyen\\temp\\acu_logs"
    assert any("Normalized log dir: /mnt/c/Users/Vien.Nguyen/temp/acu_logs -> C:\\Users\\Vien.Nguyen\\temp\\acu_logs" in message for message in logs)


def test_get_normalized_path_windows_normalizes_forward_slashes(monkeypatch):
    monkeypatch.setattr(core_utils, "convert_wsl_to_win_path", lambda p: "C:/Users/Vien.Nguyen/temp/acu_logs/P_20260521_000000.txt")
    normalized = core_utils.get_normalized_path("/mnt/c/Users/Vien.Nguyen/temp/acu_logs/P_20260521_000000.txt", target_platform=core_utils.ETargetPlatform.WINDOWS, log_label="P-log input path")
    assert str(normalized) == "C:\\Users\\Vien.Nguyen\\temp\\acu_logs\\P_20260521_000000.txt"
