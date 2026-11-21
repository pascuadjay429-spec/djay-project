#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
git config --global --add safe.directory "$ROOT" 2>/dev/null || true
git config --global --add safe.directory "*" 2>/dev/null || true
git config --global user.email >/dev/null 2>&1 || git config --global user.email "storm@termux.local"
git config --global user.name  >/dev/null 2>&1 || git config --global user.name "storm-goji"
git config --global http.postBuffer 524288000
git config --global http.version HTTP/1.1
[ -d .git ] || git init
git branch -M main 2>/dev/null || true
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "Repo URL?"; read -r U; git remote add origin "$U"
fi
git add -A
git commit -m "${1:-update}" 2>/dev/null || true
echo "Push (token as password, or set GH_TOKEN=ghp_xxx)"
if [ -n "$GH_TOKEN" ]; then
  R="$(git remote get-url origin)"
  AR="$(echo "$R" | sed -E "s#https://github.com/#https://pascuadjay429-spec:${GH_TOKEN}@github.com/#")"
  git push -u "$AR" main && echo OK && exit 0
fi
for i in 1 2 3 4 5 6 7 8; do
  echo try $i
  git push -u origin main && echo OK && exit 0
  sleep 3
done
echo FAIL
exit 1
