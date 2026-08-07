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
rill_xray_agent_manager=${RILL_XRAY_AGENT_MANAGER:-/etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh}
# P0-5: candidate validation for script self-updates. Defined here (not only
# in the manager) so it is available even when the agent files are absent.
# Validation is semantic, not string matching: the candidate's integration
# block is sourced inside an isolated sandbox with fake host tooling and the
# required runtime guarantees are actually executed (real function
# definitions, host health in healthy and broken states, offline-safe
# dispatch, reconfigure transaction, uninstall two-phase contract, menu 9).
rxa_candidate_guard() {
    # Validates a freshly downloaded install.sh candidate before it is ever
    # allowed to replace the running script. Returns 0 only when every
    # integration anchor and the shell syntax check succeed.
    local candidate=${1:-} block rtmp rc
    [[ -f "${candidate}" ]] || return 1
    bash -n "${candidate}" 2>/dev/null || return 1
    grep -qx '^RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1$' "${candidate}" || return 1
    grep -qE '^[[:space:]]*9\)[[:space:]]*rxa_menu' "${candidate}" || return 1
    grep -qE '^[[:space:]]*--rill-agent-status\)[[:space:]]*rxa_dispatch' "${candidate}" || return 1
    block=$(sed -n '/^# [B]EGIN RILL XRAY AGENT INTEGRATION$/,/^# [E]ND RILL XRAY AGENT INTEGRATION$/p' "${candidate}")
    [[ -n "${block}" ]] || return 1
    rtmp=$(mktemp -d) || return 1
    if RILL_XRAY_AGENT_PROBE_BLOCK="${block}" RILL_XRAY_AGENT_PROBE_ROOT="${rtmp}" \
        bash -c '
set -u
rt=${RILL_XRAY_AGENT_PROBE_ROOT}
mkdir -p "${rt}/bin" "${rt}/cfgs" "${rt}/xraybin" "${rt}/nginxbin" "${rt}/logs" "${rt}/state" "${rt}/etc-rill/scripts"
# Fake host tooling: the probe must never touch the real system.
cat > "${rt}/bin/systemctl" <<EOF
#!/usr/bin/env bash
exit 0
EOF
cat > "${rt}/bin/xray" <<EOF
#!/usr/bin/env bash
[ "\${1}" = "run" ] && [ "\${2}" = "-test" ] && exit 0
exit 0
EOF
cat > "${rt}/bin/nginx" <<EOF
#!/usr/bin/env bash
[ "\${1}" = "-t" ] && exit 0
exit 0
EOF
cat > "${rt}/bin/ss" <<JEOF
#!/usr/bin/env bash
printf "LISTEN 0 4096 0.0.0.0:60000 0.0.0.0:* inet sshd\n"
printf "LISTEN 0 4096 0.0.0.0:61000 0.0.0.0:* inet sshd\n"
printf "LISTEN 0 4096 0.0.0.0:61001 0.0.0.0:* inet sshd\n"
printf "LISTEN 0 4096 0.0.0.0:61002 0.0.0.0:* inet sshd\n"
JEOF
cat > "${rt}/bin/jq" <<JQEOF
#!/usr/bin/env python3
import json,sys
args=list(sys.argv[1:])
arg={}
while "--arg" in args:
    i=args.index("--arg"); arg[args[i+1]]=args[i+2]; args=args[:i]+args[i+3:]
args=[a for a in args if not a.startswith("-") and a!="--"]
flt=args[0]
if len(args)>1:
    d=json.load(open(args[1]))
else:
    d=json.load(sys.stdin)
if flt==".":
    print(json.dumps(d,separators=(",",":"))); sys.exit(0)
name=flt.split(".")[-1].split("//")[0].strip().strip(chr(34))
if name.startswith("[$"): name=arg.get(name[2:-1],"")
if isinstance(d,dict) and name in d: print(d[name])
JQEOF
chmod +x "${rt}"/bin/*
export PATH="${rt}/bin:${PATH}"
printf "%s\n" "{\"tls\":\"TLS\",\"port\":60000,\"reality_add_nginx\":\"off\",\"ws_port\":61000,\"grpc_port\":61001,\"xhttp_port\":61002}" > "${rt}/cfgs/install_config.json"
printf "%s\n" "not json" > "${rt}/cfgs/broken.json"
cp "${rt}/bin/xray" "${rt}/xraybin/xray"
cp "${rt}/bin/nginx" "${rt}/nginxbin/nginx"
printf "%s\n" "{}" > "${rt}/cfgs/xray.json"
printf "%s\n" "{}" > "${rt}/cfgs/nginx.conf"
export RILL_XRAY_AGENT_INSTALL_CONFIG="${rt}/cfgs/install_config.json"
export RILL_XRAY_AGENT_XRAY_BIN="${rt}/xraybin/xray"
export RILL_XRAY_AGENT_XRAY_CONF="${rt}/cfgs/xray.json"
export RILL_XRAY_AGENT_NGINX_BIN="${rt}/nginxbin/nginx"
export RILL_XRAY_AGENT_NGINX_CONF="${rt}/cfgs/nginx.conf"
export RILL_XRAY_AGENT_LOG_DIR="${rt}/logs"
export RILL_XRAY_AGENT_CONFIG="${rt}/cfgs/config.json"
export RILL_XRAY_AGENT_HOME="${rt}/etc-rill"
export RILL_XRAY_AGENT_STATE="${rt}/state"
export RILL_XRAY_AGENT_MANAGER="${rt}/etc-rill/scripts/rill_xray_agent_manager.sh"
export RILL_XRAY_AGENT_STATUS="${rt}/status/xray-observation.json"
export _TEST_MODE=1
menu_pause(){ return 0; }
eval "${RILL_XRAY_AGENT_PROBE_BLOCK}" || exit 1
# 1) real function definitions, not comment strings.
for f in rxa_candidate_guard rxa_uninstall_prepare rxa_uninstall_commit \
         rxa_uninstall_abort rxa_uninstall_finish rxa_reconfigure_enter \
         rxa_reconfigure_leave rxa_host_healthy rxa_dispatch rxa_menu; do
    declare -F "$f" >/dev/null 2>&1 || exit 2
done
# 2) healthy host must be real, not the old any-active shortcut.
rxa_host_healthy || exit 3
# 3) unparseable config must be refused.
RILL_XRAY_AGENT_INSTALL_CONFIG="${rt}/cfgs/broken.json" rxa_host_healthy && exit 4
# 4) missing xray binary must be refused.
RILL_XRAY_AGENT_XRAY_BIN="${rt}/nonexistent" rxa_host_healthy && exit 4
# 5) offline-safe dispatch must really run and emit the observe JSON.
out=$(rxa_dispatch status) || exit 5
case "$out" in *installed*) ;; *) exit 6 ;; esac
# 6) reconfigure hooks are non-fatal with no agent state.
rxa_reconfigure_enter || exit 7
rxa_reconfigure_leave 0 || exit 7
# 7) uninstall contract: prepare no-op without Rill; commit fails safe when
#    the purge script is absent; abort keeps the host rc and finish routes 1.
rxa_uninstall_prepare || exit 8
rxa_uninstall_commit && exit 9
rxa_uninstall_finish 1
[ $? -eq 1 ] || exit 10
# 8) menu case 9 target must be a real function.
rxa_menu >/dev/null 2>&1 || exit 11
exit 0
'; then
        rc=0
    else
        rc=$?
    fi
    rm -rf "${rtmp}"
    return "${rc}"
}
rxa_integration_self_check() {
    # Test-only / read-only contract self-check. Emits a JSON object that the
    # candidate guard and CI can parse. No side effects: it never installs,
    # never touches the network, and never modifies host state. The booleans
    # reflect what THIS integration block actually provides (schema marker,
    # hook functions, host health contract, two-phase uninstall).
    local schema=0 menu=0 box=0 flow=0
    local block file
    file="${BASH_SOURCE[0]:-}"
    block=$(sed -n '/^# [B]EGIN RILL XRAY AGENT INTEGRATION$/,/^# [E]ND RILL XRAY AGENT INTEGRATION$/p' "$file")
    grep -qx '^RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1$' "$file" >/dev/null 2>&1 && schema=1
    [[ "$block" == *rxa_menu* && "$file" != "" ]] && menu=1
    grep -qE '^[[:space:]]*--rill-agent-status\)[[:space:]]*rxa_dispatch' "$file" >/dev/null 2>&1 && menu=1
    [[ "$block" == *rxa_uninstall_prepare* && "$block" == *rxa_uninstall_commit* \
       && "$block" == *rxa_uninstall_abort* && "$block" == *rxa_uninstall_finish* ]] && box=1
    [[ "$block" == *rxa_host_healthy* && "$block" == *rxa_reconfigure_enter* \
       && "$block" == *rxa_reconfigure_leave* ]] && flow=1
    printf '{"schemaVersion":1,"integrationSchema":%d,"menuDispatch":%s,"offlineDispatch":%s,"reconfigureHooks":%s,"uninstallHooks":%s,"hostHealthContract":%s}\n' \
        "${schema}" \
        "$([[ $menu -eq 1 ]] && echo true || echo false)" \
        "$([[ $menu -eq 1 ]] && echo true || echo false)" \
        "$([[ $flow -eq 1 ]] && echo true || echo false)" \
        "$([[ $box -eq 1 ]] && echo true || echo false)" \
        "$([[ $flow -eq 1 ]] && echo true || echo false)"
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
# Paths honour RILL_XRAY_AGENT_* + DESTDIR (same sandbox semantics as the
# agent scripts) so confirm tests and _TEST_MODE runs never touch /etc,/var.
rxa_root() { printf '%s%s' "${DESTDIR:-}" "$1"; }
rxa_agent_dir(){ printf '%s%s' "${DESTDIR:-}" "${RILL_XRAY_AGENT_HOME:-/etc/rill-xray-agent}"; }
rxa_observe_out(){ printf '%s%s' "${DESTDIR:-}" "${RILL_XRAY_AGENT_STATUS:-/var/lib/rill-xray-agent-xray/status/xray-observation.json}"; }
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
        RILL_XRAY_AGENT_OUTPUT="$(rxa_observe_out)" \
            bash "$(rxa_agent_dir)/scripts/rill_xray_agent_observe.py" >/dev/null 2>&1 || true
        return 0
    fi
    if [[ "$rc" == 0 ]]; then
        echo 'Rill Xray Agent: host health check failed; staying observe-only' >&2
        RILL_XRAY_AGENT_OUTPUT="$(rxa_observe_out)" \
            bash "$(rxa_agent_dir)/scripts/rill_xray_agent_observe.py" >/dev/null 2>&1 || true
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
    local nginx_cfg="${RILL_XRAY_AGENT_NGINX_CONF:-${nginx_main_conf:-/usr/local/nginx/conf/nginx.conf}}"
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
rxa_host_post_verify() {
    # Host-uninstall post-verify: called after the host removal phase and
    # before commit. Returns 0 only when the host components are actually
    # gone. xray must be inactive and its binary removed; when nginx was
    # installed (nginx_dir present) nginx must be inactive and its binary
    # removed. Host-owned config retention is a user choice handled by the
    # caller; this function only checks what must be removed.
    local xray_bin="${RILL_XRAY_AGENT_XRAY_BIN:-${xray_bin_dir:-}/xray}"
    local nginx_bin="${RILL_XRAY_AGENT_NGINX_BIN:-${nginx_dir:-}/sbin/nginx}"
    if systemctl -q is-active xray 2>/dev/null; then
        echo 'Rill Agent: host post-verify failed: xray unit still active' >&2
        return 1
    fi
    if [[ -e "${xray_bin}" ]]; then
        echo 'Rill Agent: host post-verify failed: xray binary still present' >&2
        return 1
    fi
    if [[ -n "${nginx_dir:-}" && -d "${nginx_dir}" ]]; then
        if systemctl -q is-active nginx 2>/dev/null; then
            echo 'Rill Agent: host post-verify failed: nginx unit still active' >&2
            return 1
        fi
        if [[ -e "${nginx_bin}" ]]; then
            echo 'Rill Agent: host post-verify failed: nginx binary still present' >&2
            return 1
        fi
    fi
    return 0
}
rxa_uninstall_prepare() {
    # Two-phase uninstall, phase 1: freeze agent in observe-only, refresh the
    # observation and write a durable uninstall intent. Never deletes Rill
    # state; the host phase decides commit vs abort.
    command -v rxa_apply_mode >/dev/null 2>&1 || return 0
    local home="$(rxa_agent_dir)" state="$(rxa_root "${RILL_XRAY_AGENT_STATE:-/var/lib/rill-xray-agent-runtime}")"
    [[ -f "${home}/config.json" ]] || return 0
    rxa_apply_mode observe-only >/dev/null 2>&1 || return 1
    RILL_XRAY_AGENT_OUTPUT="$(rxa_observe_out)" \
        bash "${home}/scripts/rill_xray_agent_observe.py" >/dev/null 2>&1 || true
    install -d -m 0750 "${state}"
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"prepared","atEpochSeconds":%s}\n' "$(date +%s)" \
        > "${state}/uninstall.intent.json" 2>/dev/null || true
    return 0
}
rxa_uninstall_commit() {
    # Two-phase uninstall, phase 2: only after the host uninstall fully
    # succeeded. Writes the completion intent then executes the Rill purge.
    # Purge failure returns non-zero and is never swallowed with `|| true`.
    local pf=0
    local state="$(rxa_root "${RILL_XRAY_AGENT_STATE:-/var/lib/rill-xray-agent-runtime}")"
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"committed","atEpochSeconds":%s}\n' "$(date +%s)" \
        >> "${state}/uninstall.intent.json" 2>/dev/null || true
    bash "$(rxa_agent_dir)/scripts/rill_xray_agent_uninstall.sh" --purge || pf=$?
    if [[ "$pf" != 0 ]]; then
        echo 'Rill Xray Agent: purge failed (uninstall not completed)' >&2
        return 1
    fi
    return 0
}
rxa_uninstall_abort() {
    # Host uninstall failed: keep Runtime, audit, config and observation;
    # record the aborted intent and return the host's real non-zero code.
    local state="$(rxa_root "${RILL_XRAY_AGENT_STATE:-/var/lib/rill-xray-agent-runtime}")"
    install -d -m 0750 "${state}" 2>/dev/null || true
    printf '{"schemaVersion":1,"intent":"uninstall","phase":"aborted","atEpochSeconds":%s}\n' "$(date +%s)" \
        >> "${state}/uninstall.intent.json" 2>/dev/null || true
    echo 'Rill Agent: host uninstall failed; agent diagnostics retained' >&2
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
        text = patch_post_replace_selfcheck(text)
        return patch_uninstall_all(text)
    text = patch_update_guard(text)
    text = patch_post_replace_selfcheck(text)
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
        "        --rill-agent|--rill-agent-status|--rill-agent-safe-disable|--rill-agent-verify|--rill-agent-uninstall|\\\n"
        "        --rill-integration-self-check)",
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
        "        --rill-agent-uninstall) rxa_dispatch uninstall ;;\n"
        "        --rill-integration-self-check) rxa_integration_self_check ;;\n",
        "offline dispatch",
    )
    # P1-4: the self-check must also be dispatched before init_language /
    # check_file_integrity so stdout carries ONLY the JSON contract and it is
    # a pure, side-effect-free read. Idempotent.
    if "--rill-integration-self-check)" not in text.split("init_language")[0]:
        text = replace_once(
            text,
            "    -h|--help)\n        show_help\n        exit 0\n        ;;\nesac\n",
            "    -h|--help)\n        show_help\n        exit 0\n        ;;\n"
            "    --rill-integration-self-check)\n"
            "        # P1-4: read-only, side-effect-free contract self-check.\n"
            "        rxa_integration_self_check\n"
            "        exit 0\n"
            "        ;;\nesac\n",
            "early self-check dispatch",
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


def patch_post_replace_selfcheck(text: str) -> str:
    """P0-5 (requirement 10): after a candidate has atomically replaced the
    running script, the installed file must be re-validated (bash -n plus the
    full semantic guard) before the update is accepted. On any failure the
    previous version is restored from the update backup. Idempotent."""
    if "rxa_postreplace_selfcheck" in text:
        return text
    marker_a = '            mv -f "${_candidate}" "${idleleo}"\n            rm -f "${_backup_script}"\n'
    if marker_a in text:
        text = text.replace(
            marker_a,
            '            mv -f "${_candidate}" "${idleleo}"\n'
            '            # Rill Xray Agent: re-validate the installed script\n'
            '            # (rxa_postreplace_selfcheck); on failure restore backup.\n'
            '            if ! bash -n "${idleleo}" 2>/dev/null || ! rxa_candidate_guard "${idleleo}"; then\n'
            '                rm -f "${_candidate}"\n'
            '                [[ -n "${_backup_script}" && -f "${_backup_script}" ]] && mv -f "${_backup_script}" "${idleleo}"\n'
            '                ln -sf "${idleleo}" "${idleleo_commend_file}"\n'
            '                log_echo "${Error} ${RedBG} Rill Xray Agent $(gettext "替换后校验失败, 已回滚") ${Font}"\n'
            '                return 1\n'
            '            fi\n'
            '            rm -f "${_backup_script}"\n',
        )
    else:
        raise ValueError("post-replace mv/backup anchor not found")
    # Alternate self-update paths in idleleo_commend have no .bak; on failure
    # of the post-replace self-check we still refuse to continue. Each bare
    # mv must not already have been wrapped by the self-check above.
    count = 0
    lines = text.split("\n")
    out: list = []
    n = len(lines)
    for k in range(n):
        if lines[k] == '            mv -f "${_candidate}" "${idleleo}"':
            prev = lines[k - 1] if k > 0 else None
            nxt = lines[k + 1] if k + 1 < n else None
            already_wrapped = (
                nxt is not None
                and nxt.startswith(
                    '            # Rill Xray Agent: re-validate the installed script'
                )
            )
            if already_wrapped:
                out.append(lines[k])
                continue
            count += 1
            out.extend([
                '            mv -f "${_candidate}" "${idleleo}"',
                '            # Rill Xray Agent: re-validate the installed script',
                '            # (rxa_postreplace_selfcheck); on failure refuse to launch.',
                '            if ! bash -n "${idleleo}" 2>/dev/null || ! rxa_candidate_guard "${idleleo}"; then',
                '                rm -f "${_candidate}"',
                '                echo "Rill Xray Agent $(gettext "替换后校验失败, 已阻止启动")" >&2',
                '                return 1',
                '            fi',
            ])
        else:
            out.append(lines[k])
    text = "\n".join(out)
    if count == 0:
        raise RuntimeError("alternate post-replace mv anchor missing")
    return text


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
        # Copy only after the complete staged tree passes validation. The
        # Xray host-owned workflow (.github/workflows/rill-xray-agent.yml)
        # carries the RILL_CANONICAL_COMMIT pin and is deliberately NOT
        # overwritten: it is the consumer's trust anchor, not Rill payload.
        for rel in ("scripts", "systemd", "rill_payload", "assets", ".github", "docs"):
            staged = target / rel
            if not staged.exists():
                continue
            if rel == ".github":
                for path in staged.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.name == "rill-xray-agent.yml" and "workflows" in path.parts:
                        continue
                    destination = repo / rel / path.relative_to(staged)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
                continue
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
