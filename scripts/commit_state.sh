#!/usr/bin/env bash
# data/ papkadagi holat fayllarini repoga commit qiladi (GitHub Actions ichida).
set -uo pipefail

MSG="${1:-holat yangilandi}"

git config user.name  "fpl-uz-bot"
git config user.email "actions@users.noreply.github.com"

git add -A data/ 2>/dev/null || true

if git diff --cached --quiet; then
  echo "O'zgarish yo'q — commit qilinmadi."
  exit 0
fi

git commit -m "chore(state): ${MSG} [skip ci]" || exit 0

for i in 1 2 3; do
  git pull --rebase --autostash -q && git push -q && { echo "Holat saqlandi."; exit 0; }
  echo "Push urinishi ${i} muvaffaqiyatsiz, qayta urinamiz..."
  sleep $((i * 5))
done

echo "Ogohlantirish: holatni push qilib bo'lmadi."
exit 0
