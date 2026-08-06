#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

EXPECTED = "e3ba5d7474498fbb556b0cae741a629ebb3bf1cd"
BEGIN = "# BEGIN RILL XRAY AGENT INTEGRATION"
END = "# END RILL XRAY AGENT INTEGRATION"
BLOCK = r'''# BEGIN RILL XRAY AGENT INTEGRATION
RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1
rill_xray_agent_manager=/etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh
# P0-5: candidate validation for script self-updates. Defined here (not only
# in the manager) so it is available even when the agent files are absent.
rxa_candidate_guard() {
    local candidate=${1:-}
    [[ -f "${candidate}" ]] || return 1
    bash -n "${candidate}" 2>/dev/null || return 1
    grep -q '^RILL_XRAY_AGENT_INTEGRATION_SCHEMA=' "${candidate}" || return 1
    grep -q 'menu_item 9 "Rill Xray Agent"' "${candidate}" || return 1
    grep -q -- '--rill-agent-status' "${candidate}" || return 1
    grep -q 'rxa_reconfigure_enter()' "${candidate}" || return 1
    grep -q 'rxa_uninstall_finish()' "${candidate}" || return 1
    grep -q 'rxa_host_healthy()' "${candidate}" || return 1
    return 0
}
if [[ -f "$rill_xray_agent_manager" ]]; then
    source "$rill_xray_agent_manager"
else
    rxa_refresh_summary(){ RILL_XRAY_AGENT_HEADER_STATE='Agent: not installed'; RILL_XRAY_AGENT_HEADER_RUNTIME='Runtime: OFF'; RILL_XRAY_AGENT_HEADER_ROUTE='Route: OFF'; }
    rxa_menu(){ echo 'Rill Xray Agent is not installed. Run the included bootstrap script.'; menu_pause; }
    rxa_dispatch(){ case "${1:-}" in status) printf '%s\n' '{"installed":false,"routeAssistEnabled":false,"boundedAutoAllowed":false}' ;; install) bash "${scripts_dir}/rill_xray_agent_bootstrap.sh" ;; *) return 66 ;; esac; }
fi
# Lifecycle coordination used by the host install/update/uninstall paths.
# Every hook is non-fatal: it never changes the host transaction return code.
rxa_reconfigure_enter() {
    local cfg mode
    cfg=${RILL_XRAY_AGENT_CONFIG:-/etc/rill-xray-agent/config.json}
    command -v rxa_get >/dev/null 2>&1 || return 0
    [[ -f "$cfg" ]] || return 0
    mode=$(rxa_get mode 2>/dev/null || printf 'observe-only')
    printf '%s' "$mode" >"${cfg}.prior-mode" 2>/dev/null || true
    rxa_apply_mode observe-only >/dev/null 2>&1 || true
}
rxa_reconfigure_leave() {
    local rc=${1:-1} cfg mode
    cfg=${RILL_XRAY_AGENT_CONFIG:-/etc/rill-xray-agent/config.json}
    mode=$(cat "${cfg}.prior-mode" 2>/dev/null || printf 'observe-only')
    rm -f "${cfg}.prior-mode"
    if [[ "$rc" == 0 ]] && rxa_host_healthy; then
        rxa_apply_mode "$mode" >/dev/null 2>&1 || true
        RILL_XRAY_AGENT_OUTPUT=/var/lib/rill-xray-agent-xray/status/xray-observation.json \
            bash /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
    fi
    return 0
}
rxa_host_healthy() {
    command -v systemctl >/dev/null 2>&1 || return 0
    systemctl is-active --quiet xray 2>/dev/null && return 0
    systemctl is-active --quiet nginx 2>/dev/null && return 0
    return 1
}
rxa_uninstall_enter() {
    command -v rxa_apply_mode >/dev/null 2>&1 || return 0
    [[ -f /etc/rill-xray-agent/config.json ]] || return 0
    rxa_apply_mode observe-only >/dev/null 2>&1 || true
}
rxa_uninstall_finish() {
    local rc=${1:-1}
    if [[ "$rc" != 0 ]]; then
        echo 'Rill Xray Agent: host uninstall failed; agent diagnostics retained' >&2
        return 0
    fi
    bash /etc/rill-xray-agent/scripts/rill_xray_agent_uninstall.sh --purge || true
}
# END RILL XRAY AGENT INTEGRATION'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: anchor count={count}, expected 1")
    return text.replace(old, new, 1)


def patch(text: str) -> str:
    if BEGIN in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError("partial integration markers")
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        text = text[:start] + BLOCK + text[end:]
        return patch_update_guard(text)
    text = patch_update_guard(text)
    text = replace_once(text, "download_file() {", BLOCK + "\n\ndownload_file() {", "integration block")
    text = replace_once(
        text,
        '    menu_fields "${xray_status_field}" "${nginx_status_field}" "${connect_status_field}"\n',
        '    menu_fields "${xray_status_field}" "${nginx_status_field}" "${connect_status_field}"\n'
        '    rxa_refresh_summary\n'
        '    menu_divider "Rill Xray Agent"\n'
        '    menu_fields "${RILL_XRAY_AGENT_HEADER_STATE}" "${RILL_XRAY_AGENT_HEADER_RUNTIME}" "${RILL_XRAY_AGENT_HEADER_ROUTE}"\n',
        "header",
    )
    text = replace_once(
        text,
        '        menu_item 8 "$(gettext "修改语言") / Language"\n',
        '        menu_item 8 "$(gettext "修改语言") / Language"\n        menu_item 9 "Rill Xray Agent"\n',
        "menu item",
    )
    text = replace_once(text, "        menu_read menu_num 8\n", "        menu_read menu_num 9\n", "menu read")
    text = replace_once(text, "            8) menu_action 99 ;;\n", "            8) menu_action 99 ;;\n            9) rxa_menu ;;\n", "menu case")
    text = replace_once(
        text,
        "        --access-log|--error-log|--backup)",
        "        --access-log|--error-log|--backup|\\\n"
        "        --rill-agent|--rill-agent-status|--rill-agent-safe-disable|--rill-agent-verify|--rill-agent-uninstall)",
        "offline allow",
    )
    text = replace_once(
        text,
        "        --backup) backup_directories ;;\n",
        "        --backup) backup_directories ;;\n"
        "        --rill-agent) rxa_menu ;;\n"
        "        --rill-agent-status) rxa_dispatch status ;;\n"
        "        --rill-agent-safe-disable) rxa_dispatch mode safe-disabled ;;\n"
        "        --rill-agent-verify) rxa_dispatch verify ;;\n"
        "        --rill-agent-uninstall) rxa_dispatch uninstall ;;\n",
        "offline dispatch",
    )
    return text


def patch_update_guard(text: str) -> str:
    """P0-5: an install.sh update must download to a candidate, validate it,
    and only then atomically replace the running script. On any validation
    failure the old version is kept. Idempotent on re-apply."""
    if "install.sh.rxa-candidate" in text:
        return text
    lines = text.split("\n")
    download_line = '            download_script_file "${main_remote_url}" "${idleleo_dir}/install.sh"'
    anchors = [i for i, line in enumerate(lines) if line == download_line]
    if not anchors:
        return text
    i = anchors[0]
    j = i
    while j + 1 < len(lines) and not lines[j + 1].lstrip().startswith("downloaded_shell_version="):
        j += 1
    if j + 1 >= len(lines) or not lines[j + 1].lstrip().startswith("downloaded_shell_version="):
        raise ValueError("update_sh download span not terminated")
    new_block = [
        '            _candidate="${idleleo_dir}/install.sh.rxa-candidate.$$"',
        '            if ! download_script_file "${main_remote_url}" "${_candidate}"; then',
        '                rm -f "${_candidate}"',
        '                [[ -n "${_backup_script}" && -f "${_backup_script}" ]] && mv -f "${_backup_script}" "${idleleo}"',
        '                ln -sf "${idleleo}" "${idleleo_commend_file}"',
        '                [[ ${auto_update} == "YES" ]] && echo "$(gettext "脚本更新失败")!" >>"${log_file}"',
        '                [[ ${auto_update} != "YES" ]] && log_echo "${Error} ${RedBG} $(gettext "脚本更新失败")! ${Font}"',
        '                return 1',
        '            fi',
        '            # Rill Xray Agent: validate the candidate before it can replace',
        '            # the running script; on any failure keep the old version.',
        '            if ! command -v rxa_candidate_guard >/dev/null 2>&1 || ! rxa_candidate_guard "${_candidate}"; then',
        '                rm -f "${_candidate}"',
        '                [[ -n "${_backup_script}" && -f "${_backup_script}" ]] && mv -f "${_backup_script}" "${idleleo}"',
        '                ln -sf "${idleleo}" "${idleleo_commend_file}"',
        '                log_echo "${Error} ${RedBG} Rill Xray Agent $(gettext "集成校验失败, 已阻止脚本更新") ${Font}"',
        '                return 1',
        '            fi',
    ]
    lines = lines[:i] + new_block + lines[j + 1:]
    for k, line in enumerate(lines):
        if line.startswith("                grep -E '^shell_version='") and '${idleleo_dir}/install.sh' in line:
            lines[k] = line.replace('"${idleleo_dir}/install.sh"', '"${_candidate}"')
    joined = "\n".join(lines)
    joined = joined.replace(
        '                  "${downloaded_shell_version}" != "${newest_version}" ]]; then\n',
        '                  "${downloaded_shell_version}" != "${newest_version}" ]]; then\n'
        '                rm -f "${_candidate}"\n',
    )
    joined = joined.replace(
        '            fi\n            rm -f "${_backup_script}"\n            ln -s "${idleleo}" "${idleleo_commend_file}"\n',
        '            fi\n            mv -f "${_candidate}" "${idleleo}"\n'
        '            rm -f "${_backup_script}"\n            ln -s "${idleleo}" "${idleleo_commend_file}"\n',
    )
    # The same overwrite-before-validation defect exists in the alternate
    # self-update path (idleleo_commend) and in check_file_integrity: every
    # remaining plain download must go through the candidate + guard + move.
    plain = '            download_script_file "${main_remote_url}" "${idleleo_dir}/install.sh"'
    safe = (
        '            _candidate="${idleleo_dir}/install.sh.rxa-candidate.$$"\n'
        '            if ! download_script_file "${main_remote_url}" "${_candidate}"; then\n'
        '                rm -f "${_candidate}"\n'
        '                return 1\n'
        '            fi\n'
        '            if ! command -v rxa_candidate_guard >/dev/null 2>&1 || ! rxa_candidate_guard "${_candidate}"; then\n'
        '                rm -f "${_candidate}"\n'
        '                echo "Rill Xray Agent $(gettext "集成校验失败, 已阻止脚本更新")" >&2\n'
        '                return 1\n'
        '            fi\n'
        '            mv -f "${_candidate}" "${idleleo}"\n'
    )
    count = joined.count(plain)
    joined = joined.replace(plain, safe)
    if count == 0:
        raise ValueError("plain download line missing after update_sh patch")
    return joined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--allow-drift", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if head != EXPECTED and not args.allow_drift:
        raise SystemExit(f"upstream drift: {head}; expected {EXPECTED}")
    source = Path(__file__).resolve().parents[1] / "repository_files"
    stage = Path(tempfile.mkdtemp(prefix="rill-xray-agent-"))
    try:
        target = stage / "repo"
        shutil.copytree(repo, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        install = target / "install.sh"
        install.write_text(patch(install.read_text()))
        for path in source.rglob("*"):
            if path.is_file():
                destination = target / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        subprocess.run(["bash", "-n", str(install)], check=True)
        # Copy only after the complete staged tree passes validation.
        for rel in ("scripts", "systemd", "rill_payload", "assets", ".github", "docs"):
            staged = target / rel
            if staged.exists():
                shutil.copytree(staged, repo / rel, dirs_exist_ok=True)
        temp_install = repo / "install.sh.rxa.tmp"
        temp_install.write_text(install.read_text())
        os.chmod(temp_install, 0o755)
        os.replace(temp_install, repo / "install.sh")
        print(json.dumps({"ok": True, "base": head, "changed": True}, sort_keys=True))
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
