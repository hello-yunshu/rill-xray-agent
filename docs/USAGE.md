# Usage

```bash
python3 scripts/run_all_checks.py
git init -b main
git add .
git commit -m "feat: initialize Rill Xray Agent"
gh repo create hello-yunshu/rill-xray-agent --private --source=. --remote=origin --push
```

For the Xray repository:

```bash
git switch -c feat/rill-xray-agent e3ba5d7474498fbb556b0cae741a629ebb3bf1cd
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/verify_repo.py .
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/apply_to_repo.py .
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/verify_repo.py . --post-integration
```
