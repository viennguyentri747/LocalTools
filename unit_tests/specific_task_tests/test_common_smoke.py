import shutil
from pathlib import Path

from unit_tests.specific_task_tests.common import copy_events_db_for_cycle


def test_copy_events_db_for_cycle_real_copy():
    target_ip = "192.168.100.85"
    base = Path("/tmp/eventdb_real_test_pytest/cycle_1")
    program_log = Path("/tmp/eventdb_real_test_pytest/tod_program.log")
    shutil.rmtree(base.parent, ignore_errors=True)

    def _append(p: Path, m: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(m + "\n")

    copy_events_db_for_cycle(cycle=1, attempt=1, target_ip=target_ip, cycle_base=base, program_log_path=program_log, append_program_log_fn=_append, event_stage="real integration")
    dump_file = base / "custom_events_log.txt"
    print("dump:", str(dump_file))
    assert dump_file.is_file()
