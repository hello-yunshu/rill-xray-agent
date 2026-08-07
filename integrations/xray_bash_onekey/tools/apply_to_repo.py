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
    # Reconfigure transaction end. Only a clean host transaction (rc==0) that
    # passes the FULL mode-aware host health check may restore the prior mode.
    # On any health failure the agent stays observe-only, diagnostics are
    # refreshed, and the failure is recorded (the host tx return code itself
    # is untouched: this hook stays non-fatal for the enclosing function).
    local rc=${1:-1} cfg mode
    cfg=${RILL_XRAY_AGENT_CONFIG:-/etc/rill-xray-agent/config.json}
    mode=$(cat "${cfg}.prior-mode" 2>/dev/null || printf 'observe-only')
    rm -f "${cfg}.prior-mode"
    if [[ "$rc" == 0 ]] && rxa_host_healthy; then
        rxa_apply_mode "$mode" >/dev/null 2>&1 || true
        RILL_XRAY_AGENT_OUTPUT=/var/lib/rill-xray-agent-xray/status/xray-observation.json \
            bash /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
        return 0
    fi
    if [[ "$rc" == 0 ]]; then
        echo 'Rill Xray Agent: host health check failed; staying observe-only' >&2
        RILL_XRAY_AGENT_OUTPUT=/var/lib/rill-xray-agent-xray/status/xray-observation.json \
            bash /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
        return 1
    fi
    return 0
}
rxa_host_healthy() {
    # Mode-aware host health check. The required components are derived only
    # from install_config.json and the active install mode. Returns 0 only
    # when every required component is verifiably healthy. Untestable states
    # (systemctl/binary/config missing, config unparseable) are NEVER
    # "healthy": they return 1. Modes that do not require Nginx must not
    # require it here.
    local cfg="${RILL_XRAY_AGENT_INSTALL_CONFIG:-${xray_install_config_file:-}}"
    local xray_bin="${RILL_XRAY_AGENT_XRAY_BIN:-${xray_bin_dir:-}/xray}"
    local xray_cfg="${RILL_XRAY_AGENT_XRAY_CONF:-${xray_conf:-}}"
    local nginx_bin="${RILL_XRAY_AGENT_NGINX_BIN:-${nginx_dir:-}/sbin/nginx}"
    local nginx_cfg="${RILL_XRAY_AGENT_NGINX_CONF:-${nginx_conf_dir:-}/nginx.conf}"
    local logs="${RILL_XRAY_AGENT_LOG_DIR:-/etc/idleleo/logs}"
    local json tls reality nginx_required=0 mark port
    command -v systemctl >/dev/null 2>&1 || return 1
    [[ -n "$cfg" && -f "$cfg" ]] || return 1
    json=$(jq -c . "$cfg" 2>/dev/null) || return 1
    tls=$(printf '%s' "$json" | jq -r '.tls // empty' 2>/dev/null)
    reality=$(printf '%s' "$json" | jq -r '.reality_add_nginx // empty' 2>/dev/null)
    [[ "$tls" == "TLS" || "$reality" == "on" ]] && nginx_required=1
    [[ -x "$xray_bin" ]] || return 1
    [[ -f "$xray_cfg" ]] || return 1
    "$xray_bin" run -test -config "$xray_cfg" >/dev/null 2>&1 || return 1
    systemctl -q is-active xray 2>/dev/null || return 1
    port=$(printf '%s' "$json" | jq -r '.port // empty' 2>/dev/null)
    if [[ -n "$port" && "$port" != "null" ]]; then
        if ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}\$"; then
            echo "Rill Xray Agent: Xray port ${port} not listening" >&2
            return 1
        fi
    fi
    for mark in update_failed.mark restore_failed.mark rollback_unverified.mark; do
        [[ -f "${logs}/${mark}" ]] && return 1
    done
    if (( nginx_required )); then
        [[ -x "$nginx_bin" ]] || return 1
        "$nginx_bin" -t -c "$nginx_cfg" >/dev/null 2>&1 || return 1
        systemctl -q is-active nginx 2>/dev/null || return 1
        for port in ws_port grpc_port xhttp_port; do
            port=$(printf '%s' "$json" | jq -r --arg k "$port" '.[$k] // empty' 2>/dev/null)
            if [[ -n "$port" && "$port" != "null" ]]; then
                if ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}\$"; then
                    echo "Rill Xray Agent: Nginx port ${port} not listening" >&2
                    return 1
                fi
            fi
        done
    fi
    return 0
}
rxa_uninstall_prepare() {
    # Two-phase uninstall, phase 1: freeze agent in observe-only, refresh the
    # observation and write a durable uninstall intent. Never deletes Rill
    # state; the host phase decides commit vs abort.
    command -v rxa_apply_mode >/dev/null 2>&1 || return 0
    [[ -f /etc/rill-xray-agent/config.json ]] || return 0
    rxa_apply_mode observe-only >/dev/null 2>&1 || return 1
    RILL_XRAY_AGENT_OUTPUT=/var/lib/rill-xray-agent-xray/status/xray-observation.json \
        bash /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
    install -d -m 0750 /var/lib/rill-xray-agent-runtime
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"prepared","atEpochSeconds":%s}\n' "$(date +%s)" \
        > /var/lib/rill-xray-agent-runtime/uninstall.intent.json 2>/dev/null || true
    return 0
}
rxa_uninstall_commit() {
    # Two-phase uninstall, phase 2: only after the host uninstall fully
    # succeeded. Writes the completion intent then executes the Rill purge.
    # Purge failure returns non-zero and is never swallowed with `|| true`.
    local pf=0
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"committed","atEpochSeconds":%s}\n' "$(date +%s)" \
        >> /var/lib/rill-xray-agent-runtime/uninstall.intent.json 2>/dev/null || true
    bash /etc/rill-xray-agent/scripts/rill_xray_agent_uninstall.sh --purge || pf=$?
    if [[ "$pf" != 0 ]]; then
        echo 'Rill Xray Agent: purge failed (uninstall not completed)' >&2
        return 1
    fi
    return 0
}
rxa_uninstall_abort() {
    # Host uninstall failed: keep Runtime, audit, config and observation;
    # record the aborted intent and return the host's real non-zero code.
    install -d -m 0750 /var/lib/rill-xray-agent-runtime 2>/dev/null || true
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"aborted","atEpochSeconds":%s}\n' "$(date +%s)" \
        >> /var/lib/rill-xray-agent-runtime/uninstall.intent.json 2>/dev/null || true
    echo 'Rill Xray Agent: host uninstall failed; agent diagnostics retained' >&2
    return 1
}
rxa_uninstall_finish() {
    # Called by uninstall_all() with the accumulated host phase rc. 0 routes
    # to commit (purge), anything else aborts and keeps all diagnostics.
    local rc=${1:-1}
    if [[ "$rc" == 0 ]]; then
        rxa_uninstall_commit
    else
        rxa_uninstall_abort
        return 1
    fi
}
# END RILL XRAY AGENT INTEGRATION'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: anchor count={count}, expected 1")
    return text.replace(old, new, 1)


def patch_uninstall_all(text: str) -> str:
    """P0-x: uninstall_all() must accumulate the return codes of every
    critical host step and route the real rc into the two-phase Rill uninstall
    contract (prepare -> commit/abort). Idempotent on re-apply."""
    if "local rxa_uninstall_rc=0" in text:
        return text
    text = replace_once(
        text,
        "    rxa_uninstall_enter\n    stop_service_all\n    acme_cron_cleanup\n",
        "    rxa_uninstall_prepare\n"
        "    local rxa_uninstall_rc=0\n"
        "    stop_service_all || rxa_uninstall_rc=1\n"
        "    acme_cron_cleanup || rxa_uninstall_rc=1\n",
        "uninstall prepare",
    )
    text = replace_once(
        text,
        "    [[ -f \"${xray_bin_dir}/xray\" ]] && uninstall_xray\n",
        "    if [[ -f \"${xray_bin_dir}/xray\" ]]; then\n"
        "        uninstall_xray || rxa_uninstall_rc=1\n"
        "    fi\n",
        "uninstall xray rc",
    )
    text = replace_once(
        text,
        "    [[ -d \"${nginx_dir}\" ]] && uninstall_nginx --force\n",
        "    if [[ -d \"${nginx_dir}\" ]]; then\n"
        "        uninstall_nginx --force || rxa_uninstall_rc=1\n"
        "    fi\n",
        "uninstall nginx rc",
    )
    # daemon-reload inside uninstall_all happens twice (delete-all and
    # keep-scripts branches); both must contribute to the accumulated rc.
    text = text.replace(
        "        systemctl daemon-reload\n",
        "        systemctl daemon-reload || rxa_uninstall_rc=1\n",
    )
    # delete-all branch must not mask a failed commit/abort with exit 0.
    if text.count("        rxa_uninstall_finish 0\n") >= 2:
        text = text.replace(
            "        rxa_uninstall_finish 0\n        exit 0\n",
            "        rxa_uninstall_finish \"$rxa_uninstall_rc\"\n        exit \"$?\"\n",
        )
        text = text.replace(
            "    rxa_uninstall_finish 0\n",
            "    rxa_uninstall_finish \"$rxa_uninstall_rc\"\n",
        )
    else:
        raise ValueError(
            "uninstall_all delete-all branch pattern not found; "
            "refusing to leave exit-0 masking in place"
        )
    return text


def patch(text: str) -> str:
    if BEGIN in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError("partial integration markers")
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        text = text[:start] + BLOCK + text[end:]
        text = patch_update_guard(text)
        return patch_uninstall_all(text)
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
